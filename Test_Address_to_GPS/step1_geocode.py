#!/usr/bin/env python3
"""
使用 Nominatim (OpenStreetMap) API 将 ppr-group-25208508-test.csv 中的地址批量转换为经纬度，
并写入当前目录下的 geocoded-test-*.csv。

注意：Nominatim 对请求频率和 User-Agent 有严格要求，这里按照至少 1 秒/请求限制。
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
MAPBOX_GEOCODE_URL = "https://api.mapbox.com/search/geocode/v6/forward"


def build_query(address: str, county: str, country: str = "Ireland") -> str:
    address = (address or "").strip()
    county = (county or "").strip()
    if not address:
        return ""
    if county and county.lower() not in address.lower():
        return f"{address}, {county}, {country}"
    return f"{address}, {country}"


def query_nominatim(q: str, timeout: float = 20.0) -> Dict[str, Any]:
    params = {
        "q": q,
        "format": "json",
        "limit": 1,
        "addressdetails": 0,
    }
    url = f"{NOMINATIM_URL}?{urlencode(params)}"
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
        return result

    result["nominatim_called"] = True
    try:
        payload = query_nominatim(q=query, timeout=timeout)
        if payload:
            first = payload[0]
            result["geocode_status"] = "ok_nominatim"
            result["latitude"] = first.get("lat") or ""
            result["longitude"] = first.get("lon") or ""
            result["provider"] = "nominatim"
        else:
            result["geocode_status"] = "no_result"
    except (HTTPError, URLError, TimeoutError):
        result["geocode_status"] = "error"
    except Exception:
        result["geocode_status"] = "error"

    if result["geocode_status"].startswith("ok") and result["latitude"] and result["longitude"]:
        return result

    if not mapbox_token:
        return result
    result["mapbox_called"] = True
    try:
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
            result["geocode_status"] = "ok_mapbox_strict"
            result["latitude"] = coords["latitude"]
            result["longitude"] = coords["longitude"]
            result["provider"] = "mapbox"
            return result

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
            result["geocode_status"] = "ok_mapbox_relaxed"
            result["latitude"] = coords["latitude"]
            result["longitude"] = coords["longitude"]
            result["provider"] = "mapbox"
    except Exception as exc:
        print(f"    Mapbox 查询 {query!r} 时发生错误：{exc}", file=sys.stderr)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "使用 Nominatim (必选) + Mapbox (可选兜底) 对 ppr-group-25208508-test.csv 做地理编码。"
        )
    )
    parser.add_argument(
        "--input",
        default="../ppr-group-25208508-test.csv",
        help="输入 CSV 路径（默认：脚本上级目录中的 ppr-group-25208508-test.csv）。",
    )
    parser.add_argument(
        "--output",
        default="geocoded-test",
        help="输出 CSV 前缀（默认：geocoded-test，会自动加上时间与 .csv 后缀）。",
    )
    parser.add_argument("--limit", type=int, default=None, help="最多处理多少行；不传则处理整个文件。")
    parser.add_argument("--country", default="ie", help="国家过滤（ISO 3166-1 alpha-2，默认 ie）。")
    parser.add_argument(
        "--mapbox-token",
        default=os.getenv("MAPBOX_ACCESS_TOKEN"),
        help="Mapbox token（可选，用于在 Nominatim 无结果时兜底）。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    input_path = script_dir / args.input
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = script_dir / f"{args.output}-{timestamp}.csv"

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

        all_rows = list(reader)
        total_rows = len(all_rows)
        total_to_process = total_rows if args.limit is None else min(total_rows, args.limit)
        print(f"本次计划处理 {total_to_process} 条数据（CSV 共 {total_rows} 条记录，不含表头）。", file=sys.stderr)

        fieldnames = list(reader.fieldnames) + ["geocode_status", "latitude", "longitude", "geocode_provider"]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        processed = queried = success = no_result = error = empty_query = success_with_coords = 0
        nominatim_calls = mapbox_calls = nominatim_success = mapbox_success_strict = mapbox_success_relaxed = 0

        for row in all_rows:
            if args.limit is not None and processed >= args.limit:
                break
            current_index = processed + 1
            county_val = (row.get("County") or "").strip().lower()
            if county_val != "dublin":
                row.update({"geocode_status": "", "latitude": "", "longitude": "", "geocode_provider": ""})
                writer.writerow(row)
                processed += 1
                print(
                    f"第 {current_index}/{total_to_process} 条：County 非 Dublin，跳过地理编码。 "
                    f"[Nominatim 调用：{nominatim_calls}，Mapbox 调用：{mapbox_calls}，当前成功条数（有经纬度）：{success_with_coords}]",
                    file=sys.stderr,
                )
                continue

            res = geocode_row(row, timeout=20.0, mapbox_token=args.mapbox_token, country=args.country)
            status = res["geocode_status"]
            if status != "empty_query":
                queried += 1
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
            if res["latitude"] and res["longitude"]:
                success_with_coords += 1

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
                f"[Nominatim 调用：{nominatim_calls}，Mapbox 调用：{mapbox_calls}，当前成功条数（有经纬度）：{success_with_coords}]",
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
            if status != "empty_query":
                time.sleep(1.0)

    print(f"Done. Wrote {processed} rows to {output_path}")
    print("Summary:")
    print(f"- rows_queried (行级别发起查询的条数): {queried}")
    print(f"- success (最终状态为 ok 的条数): {success}")
    print(f"- success_with_coords (有经纬度的条数): {success_with_coords}")
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

