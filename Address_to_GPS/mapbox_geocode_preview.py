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
        "feature_id": feature.get("id", ""),
        "place_name": feature.get("place_name", ""),
        "match_code": json.dumps(props.get("match_code", {}), ensure_ascii=True),
        "error": "",
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
        "feature_id": "",
        "place_name": "",
        "match_code": "",
        "error": "",
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
        default="COMP47350_DataAnalysis/Address_to_GPS/ppr-group-25208508-train-lab3-preview-geocoded-1000.csv",
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
            "mapbox_feature_id",
            "mapbox_place_name",
            "mapbox_match_code",
            "geocode_error",
        ]
        # Keep output fixed at longitude; drop all fields after it.
        out_fields = full_out_fields[: full_out_fields.index("longitude") + 1]

        with output_path.open("w", newline="", encoding="utf-8") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=out_fields)
            writer.writeheader()

            processed = 0
            queried = 0
            success = 0
            no_result = 0
            error = 0
            empty_query = 0
            for idx, row in enumerate(reader):
                if idx >= args.limit:
                    break

                query = build_query(row, args.address_col, args.county_col)
                result = {
                    "status": "empty_query",
                    "latitude": "",
                    "longitude": "",
                    "feature_id": "",
                    "place_name": "",
                    "match_code": "",
                    "error": "",
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
                        result["error"] = str(exc)

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
                row["mapbox_feature_id"] = result["feature_id"]
                row["mapbox_place_name"] = result["place_name"]
                row["mapbox_match_code"] = result["match_code"]
                row["geocode_error"] = result["error"]
                writer.writerow({k: row.get(k, "") for k in out_fields})

                processed += 1
                if args.sleep > 0:
                    time.sleep(args.sleep)
                if processed % 50 == 0:
                    print(f"Processed {processed} rows...")

    print(f"Done. Wrote {processed} rows to: {output_path}")
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
