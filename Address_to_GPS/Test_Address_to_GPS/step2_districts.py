#!/usr/bin/env python3
"""
根据经纬度查询反向地理编码接口，只提取都柏林的行政区（Dublin District）。
测试集版本：默认输入 geocoded-test-*.csv，输出 districted-test-*.csv。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen


NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
MAPBOX_GEOCODE_URL = "https://api.mapbox.com/geocoding/v5/mapbox.places"


@dataclass
class DublinDistrictResult:
    lat: float
    lon: float
    is_dublin: bool
    district_code: str
    raw_postcode: str
    raw_address: Dict[str, Any]
    raw_payload: Dict[str, Any]
    provider: str = ""
    mapbox_called: bool = False
    nominatim_called: bool = False


def _reverse_geocode(lat: float, lon: float, timeout: float = 20.0) -> Dict[str, Any]:
    params = {
        "lat": f"{lat:.7f}",
        "lon": f"{lon:.7f}",
        "format": "json",
        "addressdetails": 1,
    }
    email = os.getenv("NOMINATIM_EMAIL", "").strip()
    if email:
        params["email"] = email
        ua = f"COMP47350-DataAnalysis-reverse/1.0 ({email})"
    else:
        ua = "COMP47350-DataAnalysis-reverse/1.0 (no-email-provided)"
    url = f"{NOMINATIM_REVERSE_URL}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": ua})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _reverse_geocode_mapbox(lat: float, lon: float, token: str, timeout: float = 20.0) -> Dict[str, Any]:
    coordinate = f"{lon:.6f},{lat:.6f}"
    params = {"types": "postcode,place,region", "access_token": token}
    url = f"{MAPBOX_GEOCODE_URL}/{coordinate}.json?{urlencode(params)}"
    with urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_dublin_district_from_postcode(postcode: str) -> str:
    token = (postcode or "").strip()
    if not token:
        return ""
    token = token.split()[0]
    if not token or token[0].upper() != "D":
        return ""
    code = token[1:]
    if not code:
        return ""
    district = code[:2] if len(code) >= 2 else code
    if len(district) >= 2 and district[0] == "0":
        return district[1]
    return district


def get_dublin_district(lat: float, lon: float, timeout: float = 20.0, token: Optional[str] = None) -> DublinDistrictResult:
    mapbox_called_flag = False
    if token:
        try:
            mapbox_called_flag = True
            payload_mb = _reverse_geocode_mapbox(lat=lat, lon=lon, token=token, timeout=timeout)
            features = payload_mb.get("features", []) or []
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
            pass

    payload = _reverse_geocode(lat=lat, lon=lon, timeout=timeout)
    address = payload.get("address", {}) or {}
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


def _to_float_or_none(value: object):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def annotate_csv_with_districts(
    input_path: Path,
    output_prefix: str = "districted-test",
    timeout: float = 20.0,
    limit: Optional[int] = None,
    mapbox_token: Optional[str] = None,
) -> Path:
    script_dir = Path(__file__).resolve().parent
    in_path = input_path if input_path.is_absolute() else script_dir / input_path
    if not in_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {in_path}")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = script_dir / f"{output_prefix}-{timestamp}.csv"

    total_target_for_log: Optional[int] = limit
    if limit is None:
        with in_path.open("r", newline="", encoding="utf-8-sig") as f_count:
            reader_count = csv.reader(f_count)
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
        total_target = total_target_for_log

        for row in reader:
            if limit is not None and processed >= limit:
                break
            processed += 1
            county_val = (row.get("County") or "").strip().lower()

            if county_val != "dublin":
                row.setdefault("dublin_district", "")
                writer.writerow(row)
                print(
                    f"第 {processed}/{total_target} 行：County 非 Dublin，跳过区划查询。"
                    f" [Mapbox 调用次数：{mapbox_calls}，Nominatim 调用次数：{nominatim_calls}，成功写入区号：{district_filled}]",
                    file=sys.stderr,
                )
                continue

            dublin_rows += 1
            lat = _to_float_or_none(row.get("latitude"))
            lon = _to_float_or_none(row.get("longitude"))
            if lat is None or lon is None:
                row["dublin_district"] = "-1"
                writer.writerow(row)
                print(
                    f"第 {processed}/{total_target} 行：经纬度无效，跳过区划查询。"
                    f" [Mapbox 调用次数：{mapbox_calls}，Nominatim 调用次数：{nominatim_calls}，成功写入区号：{district_filled}]",
                    file=sys.stderr,
                )
                continue

            try:
                result = get_dublin_district(lat=lat, lon=lon, timeout=timeout, token=mapbox_token)
            except Exception as exc:
                print(
                    f"第 {processed}/{total_target} 行：反向地理编码失败：{exc}"
                    f" [Mapbox 调用次数：{mapbox_calls}，Nominatim 调用次数：{nominatim_calls}，成功写入区号：{district_filled}]",
                    file=sys.stderr,
                )
                row["dublin_district"] = "-1"
                writer.writerow(row)
                continue

            if result.mapbox_called:
                mapbox_calls += 1
            if result.nominatim_called:
                nominatim_calls += 1

            if result.is_dublin and result.district_code:
                row["dublin_district"] = result.district_code
                district_filled += 1
                line_msg = f"Dublin 区号查询成功，district={result.district_code!r}。"
            else:
                row["dublin_district"] = "-1"
                line_msg = "在 Dublin 范围内但未能解析出区号（写入 -1）。"

            writer.writerow(row)
            print(
                f"第 {processed}/{total_target} 行：{line_msg}"
                f" [Mapbox 调用次数：{mapbox_calls}，Nominatim 调用次数：{nominatim_calls}，成功写入区号：{district_filled}]",
                file=sys.stderr,
            )
            time.sleep(1.0)

    print(
        f"完成。总行数 {processed}，Dublin 行 {dublin_rows}，成功写入区号 {district_filled}。输出文件：{out_path}",
        file=sys.stderr,
    )
    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据经纬度查询都柏林行政区，测试集批量模式。")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP 超时时间（秒）。")
    parser.add_argument(
        "--input",
        default="geocoded-test-20260324-155838.csv",
        help="输入 CSV 路径。",
    )
    parser.add_argument("--output-prefix", default="districted-test", help="输出文件前缀。")
    parser.add_argument(
        "--token",
        default=os.getenv("MAPBOX_ACCESS_TOKEN", ""),
        help="Mapbox API token（可选，提供则优先通过 Mapbox 反向地理编码获取区号）。",
    )
    parser.add_argument("--limit", type=int, default=None, help="最多处理多少行（默认：全部处理）。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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


if __name__ == "__main__":
    raise SystemExit(main())

