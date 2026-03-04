#!/usr/bin/env python3
import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

#  default=1000, 这里数量改掉,建议不要超过5000,否则可能会有请求过多被封IP的风险
GEOCODE_URL = "https://api.mapbox.com/search/geocode/v6/forward"


def _query_mapbox(query, token, country, timeout, types, autocomplete):
    params = {
        "q": query,
        "country": country,
        "types": types,
        "autocomplete": "true" if autocomplete else "false",
        "limit": 1,
        "permanent": "false",
        "access_token": token,
    }

    url = f"{GEOCODE_URL}?{urlencode(params)}"
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _feature_to_result(feature, status):
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
        "status": status,
        "latitude": lat if lat is not None else "",
        "longitude": lon if lon is not None else "",
    }


def geocode_address(query, token, country, timeout, relax_on_no_result):
    strict_payload = _query_mapbox(
        query=query,
        token=token,
        country=country,
        timeout=timeout,
        types="address",
        autocomplete=False,
    )
    strict_features = strict_payload.get("features", [])
    if strict_features:
        return _feature_to_result(strict_features[0], status="ok")

    if relax_on_no_result:
        # Fallback for area-level strings (e.g. townland/locality/place names).
        relaxed_payload = _query_mapbox(
            query=query,
            token=token,
            country=country,
            timeout=timeout,
            types="locality,place,neighborhood,district,region,postcode,street",
            autocomplete=True,
        )
        relaxed_features = relaxed_payload.get("features", [])
        if relaxed_features:
            return _feature_to_result(relaxed_features[0], status="ok_relaxed_area")

    return {
        "status": "no_result",
        "latitude": "",
        "longitude": "",
    }


def build_query(row, address_col, county_col):
    address = (row.get(address_col) or "").strip()
    county = (row.get(county_col) or "").strip()
    if not address:
        return ""
    if county and county.lower() not in address.lower():
        return f"{address}, {county}"
    return address


def parse_args():
    parser = argparse.ArgumentParser(
        description="Geocode a CSV with Mapbox Geocoding API (debug-friendly default: first 1000 rows)."
    )
    parser.add_argument(
        "--input",
        default="COMP47350_DataAnalysis/ppr-group-25208508-train-lab3-preview.csv",
        help="Input CSV path.",
    )
    parser.add_argument(
        "--output",
        default="COMP47350_DataAnalysis/Address_to_GPS/ppr-group-25208508-train-lab3-preview-geocoded.csv",
        help="Output CSV path.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Maximum number of rows to process.",
    )
    parser.add_argument(
        "--address-col",
        default="Address",
        help="Address column name in input CSV.",
    )
    parser.add_argument(
        "--county-col",
        default="County",
        help="County column name in input CSV.",
    )
    parser.add_argument(
        "--country",
        default="ie",
        help="Country filter (ISO 3166-1 alpha-2). Example: ie",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("MAPBOX_ACCESS_TOKEN"),
        help="Mapbox token. Defaults to MAPBOX_ACCESS_TOKEN env var.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.05,
        help="Seconds to sleep between API requests.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--no-relax-on-no-result",
        action="store_true",
        help="Disable relaxed fallback search when strict address lookup returns no result.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing output CSV: skip completed rows and append new results.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.token:
        print(
            "Missing Mapbox token. Set MAPBOX_ACCESS_TOKEN or use --token.",
            file=sys.stderr,
        )
        return 1

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", newline="", encoding="utf-8-sig") as f_in:
        reader = csv.DictReader(f_in)
        if not reader.fieldnames:
            print("Input CSV has no header.", file=sys.stderr)
            return 1

        full_out_fields = reader.fieldnames + [
            "geocode_query",
            "geocode_status",
            "latitude",
            "longitude",
        ]
        # Keep output fixed at longitude; drop all fields after it.
        out_fields = full_out_fields[: full_out_fields.index("longitude") + 1]

        resume_skip = 0
        write_mode = "w"
        if args.resume and output_path.exists():
            with output_path.open("r", newline="", encoding="utf-8") as f_existing:
                existing_reader = csv.DictReader(f_existing)
                if not existing_reader.fieldnames:
                    print(
                        "Existing output CSV has no header. Remove it or run without --resume.",
                        file=sys.stderr,
                    )
                    return 1
                if "geocode_status" not in existing_reader.fieldnames:
                    print(
                        "Existing output CSV is missing geocode_status. Remove it or run without --resume.",
                        file=sys.stderr,
                    )
                    return 1

                for existing_row in existing_reader:
                    if (existing_row.get("geocode_status") or "").strip():
                        resume_skip += 1
                    else:
                        # Resume safely from the first non-completed row.
                        break
            write_mode = "a"

        with output_path.open(write_mode, newline="", encoding="utf-8") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=out_fields)
            if write_mode == "w":
                writer.writeheader()

            processed = 0
            queried = 0
            success = 0
            no_result = 0
            error = 0
            empty_query = 0
            for idx, row in enumerate(reader):
                if idx < resume_skip:
                    continue
                if idx >= args.limit:
                    break

                query = build_query(row, args.address_col, args.county_col)
                result = {
                    "status": "empty_query",
                    "latitude": "",
                    "longitude": "",
                }

                if query:
                    queried += 1
                    try:
                        result = geocode_address(
                            query=query,
                            token=args.token,
                            country=args.country,
                            timeout=args.timeout,
                            relax_on_no_result=not args.no_relax_on_no_result,
                        )
                    except Exception as exc:
                        result["status"] = "error"
                        print(f"Geocode error on row {idx + 1}: {exc}", file=sys.stderr)

                status = result["status"]
                if status in {"ok", "ok_relaxed_area"}:
                    success += 1
                elif status == "no_result":
                    no_result += 1
                elif status == "error":
                    error += 1
                elif status == "empty_query":
                    empty_query += 1

                row["geocode_query"] = query
                row["geocode_status"] = status
                row["latitude"] = result["latitude"]
                row["longitude"] = result["longitude"]
                writer.writerow({k: row.get(k, "") for k in out_fields})

                processed += 1
                if args.sleep > 0:
                    time.sleep(args.sleep)
                if processed % 50 == 0:
                    print(f"Processed {processed} rows...")

    print(f"Done. Wrote {processed} rows to: {output_path}")
    if args.resume and output_path.exists():
        print(f"- resumed_skip: {resume_skip}")
    print("Summary:")
    print(f"- queried: {queried}")
    print(f"- success: {success}")
    print(f"- no_result: {no_result}")
    print(f"- error: {error}")
    print(f"- empty_query: {empty_query}")
    if queried > 0:
        print(f"- success_rate: {success / queried:.2%}")
    print(
        "Note: This run used temporary geocoding mode (permanent=false). "
        "Do not treat results as long-term stored data under Mapbox terms."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
