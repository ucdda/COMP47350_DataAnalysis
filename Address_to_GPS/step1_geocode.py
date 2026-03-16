#!/usr/bin/env python3
"""
使用 Nominatim (OpenStreetMap) API 将 ppr-group-25208508-train.csv 中的地址批量转换为经纬度，
并写入当前目录下的 geocoded.csv。

注意：Nominatim 对请求频率和 User-Agent 有严格要求，这里按照至少 1 秒/请求限制。

支持参数：
- --limit：最多处理多少行（默认 300 行）
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
MAPBOX_GEOCODE_URL = "https://api.mapbox.com/search/geocode/v6/forward"


def build_query(address: str, county: str, country: str = "Ireland") -> str:
    """
    根据 Address 和 County 构造查询字符串。
    与 mapbox 脚本类似，如果 county 不在 address 文本中，则拼上 county。
    """
    address = (address or "").strip()
    county = (county or "").strip()
    if not address:
        return ""
    if county and county.lower() not in address.lower():
        return f"{address}, {county}, {country}"
    return f"{address}, {country}"


def query_nominatim(q: str, timeout: float = 20.0) -> Dict[str, Any]:
    """
    调用 Nominatim API，返回解析后的 JSON（list）。
    只取 format=json，limit=1，addressdetails=0。
    """
    params = {
        "q": q,
        "format": "json",
        "limit": 1,
        "addressdetails": 0,
    }
    url = f"{NOMINATIM_URL}?{urlencode(params)}"

    # 使用一个“看起来像浏览器”的简洁 User-Agent
    headers = {
        "User-Agent": "Mozilla/5.0 (COMP47350-DataAnalysis; +https://openstreetmap.org)"
    }
    req = Request(url, headers=headers)

    with urlopen(req, timeout=timeout) as resp:
        import json

        return json.loads(resp.read().decode("utf-8"))


def _query_mapbox(
    query: str,
    token: str,
    country: str,
    *,
    types: str,
    autocomplete: bool,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    """
    调用 Mapbox 前向地理编码 API，返回 JSON。
    这里按 preview 脚本的方式，只取一个结果。
    """
    params = {
        "q": query,
        "country": country,
        "types": types,
        "autocomplete": "true" if autocomplete else "false",
        "limit": 1,
        "permanent": "false",
        "access_token": token,
    }
    url = f"{MAPBOX_GEOCODE_URL}?{urlencode(params)}"
    with urlopen(url, timeout=timeout) as response:
        import json

        return json.loads(response.read().decode("utf-8"))


def _mapbox_feature_to_result(feature: Dict[str, Any]) -> Dict[str, Any]:
    """
    从 Mapbox 的 feature 中提取经纬度。
    """
    props = feature.get("properties", {})
    coords = props.get("coordinates", {})

    lat = coords.get("latitude")
    lon = coords.get("longitude")

    if lat is None or lon is None:
        geometry_coords = feature.get("geometry", {}).get("coordinates", [])
        if len(geometry_coords) >= 2:
            lon = geometry_coords[0]
            lat = geometry_coords[1]

    return {
        "latitude": lat if lat is not None else "",
        "longitude": lon if lon is not None else "",
    }


def geocode_row(
    row: Dict[str, str],
    timeout: float = 20.0,
    mapbox_token: str | None = None,
    country: str = "ie",
) -> Dict[str, Any]:
    """
    对单行做地理编码：
    1) 先用 Nominatim 查；
    2) 如果 Nominatim 没有成功找到（status 不是 ok 或没有坐标），并且配置了 Mapbox token，
       则再用 Mapbox 做一次查询。

    返回：
    {
        geocode_query, geocode_status, latitude, longitude,
        provider,                # "nominatim" / "mapbox" / ""
        nominatim_called: bool,
        mapbox_called: bool,
    }
    """
    address = row.get("Address", "")
    county = row.get("County", "")
    query = build_query(address, county)

    result: Dict[str, Any] = {
        "geocode_status": "empty_query",
        "latitude": "",
        "longitude": "",
        "provider": "",
        "nominatim_called": False,
        "mapbox_called": False,
    }

    if not query:
        # 具体日志放在主循环里统一输出
        return result

    # 1) 先调用 Nominatim
    result["nominatim_called"] = True

    try:
        payload = query_nominatim(q=query, timeout=timeout)
        if payload:
            first = payload[0]
            lat = first.get("lat")
            lon = first.get("lon")
            # 严格 Nominatim 命中
            result["geocode_status"] = "ok_nominatim"
            result["latitude"] = lat or ""
            result["longitude"] = lon or ""
            result["provider"] = "nominatim"
        else:
            result["geocode_status"] = "no_result"
    except (HTTPError, URLError, TimeoutError) as exc:  # type: ignore[misc]
        # 具体错误信息在主循环中不逐条展开
        result["geocode_status"] = "error"
    except Exception as exc:  # 防御性兜底
        # 只在需要调试时再查看具体异常
        result["geocode_status"] = "error"

    # 如果 Nominatim 成功并且拿到了坐标，就直接返回
    if result["geocode_status"].startswith("ok") and result["latitude"] and result["longitude"]:
        return result

    # 2) Nominatim 没成功、且有 Mapbox token 时，调用 Mapbox 兜底
    if not mapbox_token:
        return result
    result["mapbox_called"] = True

    try:
        # 1) 先严格按地址匹配（不自动补全）
        strict_payload = _query_mapbox(
            query=query,
            token=mapbox_token,
            country=country.upper(),
            types="address",
            autocomplete=False,
            timeout=timeout,
        )
        strict_features = strict_payload.get("features", [])

        if strict_features:
            coords = _mapbox_feature_to_result(strict_features[0])
            # Mapbox 严格地址命中
            result["geocode_status"] = "ok_mapbox_strict"
            result["latitude"] = coords["latitude"]
            result["longitude"] = coords["longitude"]
            result["provider"] = "mapbox"
            return result

        # 2) 严格匹配失败时做“松弛”：允许 locality/place/region 等，并开启自动补全
        relaxed_payload = _query_mapbox(
            query=query,
            token=mapbox_token,
            country=country.upper(),
            types="locality,place,neighborhood,district,region,postcode,street",
            autocomplete=True,
            timeout=timeout,
        )
        relaxed_features = relaxed_payload.get("features", [])
        if relaxed_features:
            coords = _mapbox_feature_to_result(relaxed_features[0])
            # Mapbox 松弛（区域级别）命中
            result["geocode_status"] = "ok_mapbox_relaxed"
            result["latitude"] = coords["latitude"]
            result["longitude"] = coords["longitude"]
            result["provider"] = "mapbox"
        # 如果松弛后也没有结果，就保持原来的 status（可能是 no_result / error）
    except Exception as exc:
        print(f"    Mapbox 查询 {query!r} 时发生错误：{exc}", file=sys.stderr)
        # 避免覆盖前面 Nominatim 的状态，这里只追加日志

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "使用 Nominatim (必选) + Mapbox (可选兜底) 对 ppr-group-25208508-train.csv 做地理编码。"
        )
    )
    parser.add_argument(
        "--input",
        default="../ppr-group-25208508-train.csv",
        help="输入 CSV 路径（默认：脚本上级目录中的 ppr-group-25208508-train.csv）。",
    )
    parser.add_argument(
        "--output",
        default="geocoded",
        help="输出 CSV 前缀（默认：geocoded，会自动加上时间与 .csv 后缀）。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多处理多少行；不传则处理整个文件。",
    )
    parser.add_argument(
        "--country",
        default="ie",
        help="国家过滤（ISO 3166-1 alpha-2，默认 ie）。",
    )
    parser.add_argument(
        "--mapbox-token",
        default=os.getenv("MAPBOX_ACCESS_TOKEN"),
        help="Mapbox token（可选，用于在 Nominatim 无结果时兜底）。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # 输入 / 输出文件（都基于当前脚本所在目录）
    script_dir = Path(__file__).resolve().parent
    input_path = script_dir / args.input
    # 每次运行根据时间生成一个唯一文件名，例如 geocoded-20260310-153045.csv
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_stem = args.output  # 可以是前缀/path，不含后缀
    output_path = script_dir / f"{output_stem}-{timestamp}.csv"

    if not input_path.exists():
        print(f"输入文件不存在: {input_path}", file=sys.stderr)
        return 1

    with input_path.open("r", newline="", encoding="utf-8-sig") as f_in, output_path.open(
        "w", newline="", encoding="utf-8"
    ) as f_out:
        reader = csv.DictReader(f_in)
        if not reader.fieldnames:
            print("输入 CSV 没有表头。", file=sys.stderr)
            return 1

        # 先把所有行读到列表，方便知道总共有多少条数据
        all_rows = list(reader)
        total_rows = len(all_rows)
        total_to_process = total_rows if args.limit is None else min(total_rows, args.limit)
        print(
            f"本次计划处理 {total_to_process} 条数据（CSV 共 {total_rows} 条记录，不含表头）。",
            file=sys.stderr,
        )

        # 在原始列基础上追加 geocode 字段（不再输出 geocode_query）
        fieldnames = list(reader.fieldnames) + [
            "geocode_status",
            "latitude",
            "longitude",
            "geocode_provider",
        ]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        processed = 0
        queried = 0
        success = 0
        no_result = 0
        error = 0
        empty_query = 0
        success_with_coords = 0  # 有经纬度的数据条数
        nominatim_calls = 0
        mapbox_calls = 0
        nominatim_success = 0
        mapbox_success_strict = 0
        mapbox_success_relaxed = 0

        for row in all_rows:
            if args.limit is not None and processed >= args.limit:
                break

            # 先计算当前索引
            current_index = processed + 1
            county_val = (row.get("County") or "").strip().lower()

            # 当且仅当 County 为 Dublin 时才进行地理编码；否则原样追加（只补上空的 geocode 列）
            if county_val != "dublin":
                row.update(
                    {
                        "geocode_status": "",
                        "latitude": "",
                        "longitude": "",
                        "geocode_provider": "",
                    }
                )
                writer.writerow(row)
                processed += 1

                print(
                    f"第 {current_index}/{total_to_process} 条：County 非 Dublin，跳过地理编码。 "
                    f"[Nominatim 调用：{nominatim_calls}，Mapbox 调用：{mapbox_calls}，"
                    f"当前成功条数（有经纬度）：{success_with_coords}]",
                    file=sys.stderr,
                )
                continue

            # 只有 County 为 Dublin 的行才会走到这里，进行地理编码
            res = geocode_row(
                row,
                timeout=20.0,
                mapbox_token=args.mapbox_token,
                country=args.country,
            )
            status = res["geocode_status"]

            if status != "empty_query":
                queried += 1
            # 记录具体 API 调用次数
            if res.get("nominatim_called"):
                nominatim_calls += 1
            if res.get("mapbox_called"):
                mapbox_calls += 1

            if status.startswith("ok"):
                success += 1
                if status == "ok_nominatim":
                    nominatim_success += 1
                elif status == "ok_mapbox_strict":
                    mapbox_success_strict += 1
                elif status == "ok_mapbox_relaxed":
                    mapbox_success_relaxed += 1
            elif status == "no_result":
                no_result += 1
            elif status == "error":
                error += 1
            elif status == "empty_query":
                empty_query += 1

            # 统计真正“有坐标”的成功条数（经纬度都非空）
            if res["latitude"] and res["longitude"]:
                success_with_coords += 1

            # 每条只输出一行简洁日志，并附带当前各 API 累计调用次数。
            # geocode_status 现在区分：
            # - ok_nominatim：Nominatim 严格命中
            # - ok_mapbox_strict：Mapbox 严格地址命中
            # - ok_mapbox_relaxed：Mapbox 松弛（区域级别）命中
            if status == "empty_query":
                line_msg = "地址为空，跳过。"
            elif status == "ok_nominatim":
                line_msg = "Nominatim 成功（严格匹配）。"
            elif status == "ok_mapbox_strict":
                line_msg = "Nominatim 未成功，Mapbox 严格匹配成功。"
            elif status == "ok_mapbox_relaxed":
                line_msg = "Nominatim 未成功，Mapbox 松弛匹配成功。"
            elif status == "no_result":
                line_msg = "Nominatim 和 Mapbox 都无结果。"
            elif status == "error":
                line_msg = "Nominatim / Mapbox 请求出错。"
            else:
                line_msg = f"状态：{status}。"

            print(
                f"第 {current_index}/{total_to_process} 条：{line_msg} "
                f"[Nominatim 调用：{nominatim_calls}，Mapbox 调用：{mapbox_calls}，"
                f"当前成功条数（有经纬度）：{success_with_coords}]",
                file=sys.stderr,
            )

            row.update(
                {
                    "geocode_status": status,
                    "latitude": res["latitude"],
                    "longitude": res["longitude"],
                    "geocode_provider": res.get("provider", ""),
                }
            )
            writer.writerow(row)
            processed += 1

            # 遵守服务的速率限制：
            # 只要这一行不是 empty_query，就说明确实发出了请求，需要短暂 sleep。
            if status != "empty_query":
                time.sleep(1.0)

    print(f"Done. Wrote {processed} rows to {output_path}")
    print("Summary:")
    print(f"- rows_queried (行级别发起查询的条数): {queried}")
    print(f"- success (最终状态为 ok 的条数): {success}")
    print(f"- success_with_coords (有经纬度的条数): {success_with_coords}")
    if 'total_to_process' in locals():
        failed_no_coords = total_to_process - success_with_coords
        print(f"- failed_no_coords (没有经纬度视为失败): {failed_no_coords}")
    print(f"- no_result (API 明确返回无结果): {no_result}")
    print(f"- error (请求出错): {error}")
    print(f"- empty_query (地址为空跳过): {empty_query}")
    print(f"- nominatim_calls (Nominatim 调用次数): {nominatim_calls}")
    print(f"- nominatim_success (由 Nominatim 严格匹配成功的条数): {nominatim_success}")
    print(f"- mapbox_calls (Mapbox 调用次数): {mapbox_calls}")
    print(f"- mapbox_success_strict (Mapbox 严格匹配成功条数): {mapbox_success_strict}")
    print(f"- mapbox_success_relaxed (Mapbox 松弛匹配成功条数): {mapbox_success_relaxed}")
    if queried > 0:
        print(f"- success_rate (按行计的成功率): {success / queried:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

