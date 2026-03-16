#!/usr/bin/env python3
"""
根据经纬度查询 Nominatim 的反向地理编码接口，只提取都柏林的行政区（Dublin District）。

示例：
https://nominatim.openstreetmap.org/reverse?lat=53.3498&lon=-6.2603&format=json&addressdetails=1

返回 JSON 中的 postcode 形如 "D01 P5P5" 或 "D6W"，我们只需要其中的区号部分：
- 以字母 D/d 开头时，取其后的两位作为区号，例如：
  - "D01"  -> "1"
  - "D02"  -> "2"
  - "D08"  -> "8"
  - "D6W"  -> "6W"
  - "D12"  -> "12"
  规则：只看 D 后面连续的两位字符；如果第一位是 '0'，则只保留第二位，否则两位都保留。
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import os
import time


NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
MAPBOX_GEOCODE_URL = "https://api.mapbox.com/geocoding/v5/mapbox.places"


@dataclass
class DublinDistrictResult:
    lat: float
    lon: float
    is_dublin: bool
    district_code: str  # 例如 "1", "8", "12", "6W"；非都柏林或无法解析时为空字符串
    raw_postcode: str
    raw_address: Dict[str, Any]
    raw_payload: Dict[str, Any]
    # provider: "mapbox" / "nominatim" / ""
    provider: str = ""
    # 是否在本次查询中调用了 Mapbox / Nominatim（用于日志统计）
    mapbox_called: bool = False
    nominatim_called: bool = False


def _reverse_geocode(lat: float, lon: float, timeout: float = 20.0) -> Dict[str, Any]:
    """调用 Nominatim 反向地理编码，返回 JSON。"""
    params = {
        "lat": f"{lat:.7f}",
        "lon": f"{lon:.7f}",
        "format": "json",
        "addressdetails": 1,
    }
    url = f"{NOMINATIM_REVERSE_URL}?{urlencode(params)}"

    # 按 Nominatim 要求提供可联系的 User-Agent / email（如果用户配置了环境变量）
    email = os.getenv("NOMINATIM_EMAIL", "").strip()
    if email:
        params["email"] = email
        ua = f"COMP47350-DataAnalysis-reverse/1.0 ({email})"
    else:
        # 退而求其次，仍然提供一个清晰的标识，避免用浏览器 UA 伪装
        ua = "COMP47350-DataAnalysis-reverse/1.0 (no-email-provided)"

    # 需要在带上 email 参数后重新拼接 URL
    url = f"{NOMINATIM_REVERSE_URL}?{urlencode(params)}"

    headers = {
        "User-Agent": ua,
    }
    req = Request(url, headers=headers)

    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _reverse_geocode_mapbox(
    lat: float,
    lon: float,
    token: str,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    """
    使用 Mapbox 反向地理编码获取行政区划信息。
    这里主要关注 postcode / place / region，用于推断都柏林区号。
    """
    if not token:
        raise ValueError("Mapbox token 为空。")

    # Mapbox 反向地理编码要求经纬度顺序为 {lon},{lat}
    coordinate = f"{lon:.6f},{lat:.6f}"
    params = {
        "types": "postcode,place,region",
        "access_token": token,
    }
    url = f"{MAPBOX_GEOCODE_URL}/{coordinate}.json?{urlencode(params)}"

    with urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_dublin_district_from_postcode(postcode: str) -> str:
    """
    从 Nominatim 的 postcode 中提取都柏林区号。

    规则（仅处理形如 Dxx 或 D? 的前缀）：
    - 取第一个以空格分隔的 token，例如 "D01 P5P5" -> "D01"
    - 如果不以 D/d 开头，返回 ""。
    - 去掉开头的 D/d，得到余串 code，例如 "01"、"12"、"6W"。
    - 取 code 的前两位（如果不足两位就全取），记为 district。
      - 若 district 第一位是 '0'，则只保留第二位。
      - 否则按原样返回 district。
    """
    token = (postcode or "").strip()
    if not token:
        return ""
    token = token.split()[0]  # 只看前半部分，例如 "D01"

    if not token or token[0].upper() != "D":
        return ""

    code = token[1:]
    if not code:
        return ""

    # 只关心前两位
    if len(code) >= 2:
        district = code[:2]
    else:
        district = code

    # 如果第一位是 0，则只保留第二位（例如 "01" -> "1"）
    if len(district) >= 2 and district[0] == "0":
        return district[1]

    return district


def get_dublin_district(
    lat: float,
    lon: float,
    timeout: float = 20.0,
    token: Optional[str] = None,
) -> DublinDistrictResult:
    """
    给定经纬度，只在位于都柏林时返回区号信息。

    查询顺序：
    1）如果提供了 Mapbox token，优先使用 Mapbox 反向地理编码；
    2）如果 Mapbox 未能解析出区号，则回退到 Nominatim。

    - 如果不是都柏林，is_dublin=False，district_code=""。
    - 如果是都柏林，但 postcode 无法解析区号，也会返回 district_code=""。
    """
    mapbox_called_flag = False

    # 1) 优先尝试 Mapbox（如果提供了 token）
    if token:
        try:
            mapbox_called_flag = True
            payload_mb = _reverse_geocode_mapbox(lat=lat, lon=lon, token=token, timeout=timeout)
            features = payload_mb.get("features", []) or []

            # 找到第一个 place_type 包含 postcode 的 feature
            postcode_feature = None
            for f in features:
                if "postcode" in (f.get("place_type") or []):
                    postcode_feature = f
                    break

            raw_postcode = ""
            district_code = ""
            is_dublin = False

            if postcode_feature:
                raw_postcode = postcode_feature.get("text") or ""
                district_code = _extract_dublin_district_from_postcode(raw_postcode)

                # 判断是否位于都柏林：在 place_name 或 context 中查找 Dublin/都柏林
                ctx_texts = [postcode_feature.get("place_name", "")]
                for ctx in postcode_feature.get("context", []) or []:
                    ctx_texts.append(ctx.get("text", ""))
                ctx_all = " ".join(ctx_texts).lower()
                is_dublin = ("dublin" in ctx_all) or ("都柏林" in ctx_all)

            if is_dublin and district_code:
                return DublinDistrictResult(
                    lat=lat,
                    lon=lon,
                    is_dublin=True,
                    district_code=district_code,
                    raw_postcode=raw_postcode,
                    raw_address={},
                    raw_payload=payload_mb,
                    provider="mapbox",
                    mapbox_called=True,
                    nominatim_called=False,
                )
        except Exception:
            # Mapbox 失败时静默回退到 Nominatim
            pass

    # 2) 回退到 Nominatim
    payload = _reverse_geocode(lat=lat, lon=lon, timeout=timeout)
    address = payload.get("address", {}) or {}

    # Nominatim 里的 city/county 可能是英文 "Dublin" 或中文 "都柏林" 等
    city = (address.get("city") or address.get("town") or "").lower()
    county = (address.get("county") or "").lower()

    is_dublin = ("dublin" in city) or ("dublin" in county) or ("都柏林" in city) or ("都柏林" in county)

    raw_postcode = address.get("postcode") or ""
    district_code = _extract_dublin_district_from_postcode(raw_postcode) if is_dublin else ""

    return DublinDistrictResult(
        lat=lat,
        lon=lon,
        is_dublin=is_dublin,
        district_code=district_code,
        raw_postcode=raw_postcode,
        raw_address=address,
        raw_payload=payload,
        provider="nominatim",
        mapbox_called=mapbox_called_flag,
        nominatim_called=True,
    )


def annotate_csv_with_districts(
    input_path: Path,
    output_prefix: str = "districted",
    timeout: float = 20.0,
    limit: Optional[int] = None,
    mapbox_token: Optional[str] = None,
) -> Path:
    """
    读取 geocoded CSV，只对 County 为 Dublin 的行进行区划查询，并写出新文件。

    - 输入：包含 County、latitude、longitude 列的 CSV（例如 multi_api_calling 生成的 geocoded-*.csv）
    - 输出：同样的列 + 一个新列 dublin_district
      - 仅对 County 为 Dublin 的行调用 Nominatim 反向地理编码并写入区号
      - 其它行原样复制，dublin_district 为空
    - 输出文件名：<output_prefix>-YYYYMMDD-HHMMSS.csv，保存在当前脚本目录下
    """
    script_dir = Path(__file__).resolve().parent
    in_path = input_path if input_path.is_absolute() else script_dir / input_path

    if not in_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {in_path}")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = script_dir / f"{output_prefix}-{timestamp}.csv"

    # 为了在日志中打印“当前行 / 总行数”，如果未设置 limit，则需要先统计一次总数据行数
    total_target_for_log: Optional[int] = limit
    if limit is None:
        with in_path.open("r", newline="", encoding="utf-8-sig") as f_count:
            reader_count = csv.reader(f_count)
            # 第 1 行是表头，不算在数据行里
            first = True
            total_rows_all = 0
            for _ in reader_count:
                if first:
                    first = False
                    continue
                total_rows_all += 1
        total_target_for_log = total_rows_all

    with in_path.open("r", newline="", encoding="utf-8-sig") as f_in, out_path.open(
        "w", newline="", encoding="utf-8"
    ) as f_out:
        reader = csv.DictReader(f_in)
        if not reader.fieldnames:
            raise ValueError("输入 CSV 没有表头。")

        fieldnames = list(reader.fieldnames)
        if "dublin_district" not in fieldnames:
            fieldnames.append("dublin_district")

        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        processed = 0
        dublin_rows = 0
        district_filled = 0
        mapbox_calls = 0
        nominatim_calls = 0
        # 用于日志显示的“总共计划处理多少行”：有 limit 用 limit，否则用真实数据行数
        total_target = total_target_for_log

        for row in reader:
            # 如果设置了 limit，则在处理前先检查是否已达到上限
            if limit is not None and processed >= limit:
                break

            processed += 1
            county_val = (row.get("County") or "").strip().lower()

            # 只对 Dublin 行做行政区查询，其他行原样追加（district 为空）
            if county_val != "dublin":
                row.setdefault("dublin_district", "")
                writer.writerow(row)
                print(
                    f"第 {processed}/{total_target} 行：County 非 Dublin，跳过区划查询。"
                    f" [Mapbox 调用次数：{mapbox_calls}，Nominatim 调用次数：{nominatim_calls}，"
                    f"成功写入区号：{district_filled}]",
                    file=sys.stderr,
                )
                continue

            dublin_rows += 1

            try:
                lat_str = (row.get("latitude") or "").strip()
                lon_str = (row.get("longitude") or "").strip()
                lat = float(lat_str)
                lon = float(lon_str)
            except (TypeError, ValueError):
                # 经纬度不合法，直接留空
                row.setdefault("dublin_district", "")
                writer.writerow(row)
                print(
                    f"第 {processed}/{total_target} 行：经纬度无效，跳过区划查询。"
                    f" [Mapbox 调用次数：{mapbox_calls}，Nominatim 调用次数：{nominatim_calls}，"
                    f"成功写入区号：{district_filled}]",
                    file=sys.stderr,
                )
                continue

            # 发送区划查询（内部可能调用 Mapbox 与/或 Nominatim）
            try:
                result = get_dublin_district(lat=lat, lon=lon, timeout=timeout, token=mapbox_token)
            except Exception as exc:
                print(
                    f"第 {processed}/{total_target} 行：反向地理编码失败：{exc}"
                    f" [Mapbox 调用次数：{mapbox_calls}，Nominatim 调用次数：{nominatim_calls}，"
                    f"成功写入区号：{district_filled}]",
                    file=sys.stderr,
                )
                row.setdefault("dublin_district", "")
                writer.writerow(row)
                continue

            # 根据结果统计调用次数
            if result.mapbox_called:
                mapbox_calls += 1
            if result.nominatim_called:
                nominatim_calls += 1

            if result.is_dublin and result.district_code:
                row["dublin_district"] = result.district_code
                district_filled += 1
                line_msg = f"Dublin 区号查询成功，district={result.district_code!r}。"
            else:
                # 对 Dublin 行但未能解析出 district 的情况，写入 -1，方便后续统计 / 过滤
                row["dublin_district"] = "-1"
                line_msg = "在 Dublin 范围内但未能解析出区号（写入 -1）。"

            writer.writerow(row)

            # 每次请求后输出一行日志，风格类似 multi_api_calling.py
            print(
                f"第 {processed}/{total_target} 行：{line_msg}"
                f" [Mapbox 调用次数：{mapbox_calls}，Nominatim 调用次数：{nominatim_calls}，"
                f"成功写入区号：{district_filled}]",
                file=sys.stderr,
            )

            # 遵守服务速率限制：每次请求后睡眠 1 秒
            time.sleep(1.0)

    print(
        f"完成。总行数 {processed}，Dublin 行 {dublin_rows}，"
        f"成功写入区号 {district_filled}。输出文件：{out_path}",
        file=sys.stderr,
    )
    return out_path


def main(argv: Optional[list[str]] = None) -> int:
    """
    命令行入口：

    1）单点查询：
        python district_api.py --lat 53.3498 --lon -6.2603

    2）批量标注 CSV（推荐）：
        python district_api.py --input geocoded-20260310-215024.csv
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="根据经纬度查询都柏林行政区，支持单点和 CSV 批量模式。"
    )
    parser.add_argument("--lat", type=float, help="纬度（单点模式）")
    parser.add_argument("--lon", type=float, help="经度（单点模式）")
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP 超时时间（秒）。",
    )
    parser.add_argument(
        "--input",
        default="geocoded-20260310-215024.csv",
        help="输入 CSV 路径（默认：geocoded-20260310-215024.csv）。",
    )
    parser.add_argument(
        "--output-prefix",
        default="districted",
        help="批量模式下输出文件前缀（默认：districted）。",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("MAPBOX_ACCESS_TOKEN", ""),
        help="Mapbox API token（可选，提供则优先通过 Mapbox 反向地理编码获取区号）。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多处理多少行（默认：全部处理）。",
    )

    args = parser.parse_args(argv)

    # 批量模式：如果提供了 input，就优先按 CSV 处理
    if args.input:
        mapbox_token = args.token.strip() or None
        try:
            annotate_csv_with_districts(
                input_path=Path(args.input),
                output_prefix=args.output_prefix,
                timeout=args.timeout,
                limit=args.limit,
                mapbox_token=mapbox_token,
            )
        except Exception as exc:
            print(f"批量处理失败：{exc}", file=sys.stderr)
            return 1
        return 0

    # 否则走单点模式，需要 lat / lon
    if args.lat is None or args.lon is None:
        print("请提供 --lat 和 --lon，或提供 --input 进行批量处理。", file=sys.stderr)
        return 1

    try:
        result = get_dublin_district(lat=args.lat, lon=args.lon, timeout=args.timeout)
    except Exception as exc:
        print(f"查询失败：{exc}", file=sys.stderr)
        return 1

    if not result.is_dublin:
        print("该点不在都柏林范围内，未返回区号。")
    else:
        print(
            f"经纬度 ({result.lat}, {result.lon}) 在都柏林范围内，"
            f"postcode={result.raw_postcode!r}，解析得到区号={result.district_code!r}。"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

