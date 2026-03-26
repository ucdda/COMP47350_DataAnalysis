#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Optional


REFERENCE_LAT = 53.346423829634354
REFERENCE_LON = -6.3382375566078455


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rematch Dublin rows with dublin_district=-1 by geometric regions "
            "defined from the reference point."
        )
    )
    parser.add_argument(
        "--input",
        default="districted-test-20260324-193215.csv",
        help="Input districted CSV path.",
    )
    parser.add_argument(
        "--output-prefix",
        default="rematch-test",
        help="Output CSV prefix. Final name: <prefix>-YYYYMMDD-HHMMSS.csv",
    )
    return parser.parse_args()


def to_float_or_none(value: object) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_district_int(value: object) -> Optional[int]:
    s = (str(value).strip() if value is not None else "")
    if not s:
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def rematch_district(lat: float, lon: float) -> str:
    if lon < REFERENCE_LON:
        return "25"
    if lat >= REFERENCE_LAT:
        return "26"
    return "27"


def run(input_path: Path, output_prefix: str) -> Path:
    script_dir = Path(__file__).resolve().parent
    in_path = input_path if input_path.is_absolute() else script_dir / input_path
    if not in_path.exists():
        raise FileNotFoundError(f"Input file not found: {in_path}")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = script_dir / f"{output_prefix}-{timestamp}.csv"

    with in_path.open("r", newline="", encoding="utf-8-sig") as f_in, out_path.open(
        "w", newline="", encoding="utf-8"
    ) as f_out:
        reader = csv.DictReader(f_in)
        if not reader.fieldnames:
            raise ValueError("Input CSV has no header.")

        fieldnames = list(reader.fieldnames)
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        total_rows = 0
        target_rows = 0
        rematched_rows = 0

        for row in reader:
            total_rows += 1
            county = (row.get("County") or "").strip().lower()
            district = parse_district_int(row.get("dublin_district"))
            if county == "dublin" and district == -1:
                target_rows += 1
                lat = to_float_or_none(row.get("latitude"))
                lon = to_float_or_none(row.get("longitude"))
                if lat is not None and lon is not None:
                    row["dublin_district"] = rematch_district(lat=lat, lon=lon)
                    rematched_rows += 1
            writer.writerow(row)

    print(f"Saved rematch CSV: {out_path}")
    print(
        f"Rows={total_rows}, target(Dublin & -1)={target_rows}, "
        f"rematched(with valid lat/lon)={rematched_rows}"
    )
    return out_path


def main() -> int:
    args = parse_args()
    run(input_path=Path(args.input), output_prefix=args.output_prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

