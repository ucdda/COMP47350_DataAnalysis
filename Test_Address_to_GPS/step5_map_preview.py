#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


DUBLIN_CENTER = (53.35, -6.26)
SUCCESS_STATUSES = {"ok_nominatim", "ok_mapbox_strict", "ok_mapbox_relaxed"}
REFERENCE_POINT = (53.346423829634354, -6.3382375566078455)

COLOR_25 = "#1e88e5"
COLOR_26 = "#e53935"
COLOR_27 = "#43a047"
COLOR_OTHER = "#9e9e9e"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render rematched Dublin districts map (25/26/27)."
    )
    parser.add_argument(
        "--input",
        default="rematch-test-20260326-000126.csv",
        help="Input rematch CSV (e.g. rematch-test-YYYYMMDD-HHMMSS.csv).",
    )
    parser.add_argument(
        "--output",
        default="rematch_test_map_demo_osm.html",
        help="Output HTML path.",
    )
    return parser.parse_args()


def to_float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_district_int(value):
    s = (str(value).strip() if value is not None else "")
    if not s:
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def district_color(d):
    if d == 25:
        return COLOR_25
    if d == 26:
        return COLOR_26
    if d == 27:
        return COLOR_27
    return COLOR_OTHER


def load_dublin_points(csv_path):
    points = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        county = (row.get("County") or "").strip().lower()
        if county != "dublin":
            continue
        status = (row.get("geocode_status") or "").strip()
        lat = to_float_or_none(row.get("latitude"))
        lon = to_float_or_none(row.get("longitude"))
        if status not in SUCCESS_STATUSES or lat is None or lon is None:
            continue
        d = parse_district_int(row.get("dublin_district"))
        points.append(
            {
                "address": row.get("Address", ""),
                "county": row.get("County", ""),
                "status": status,
                "query": row.get("geocode_query", ""),
                "dublin_district": d,
                "lat": lat,
                "lon": lon,
                "color": district_color(d),
            }
        )
    return points


def center_for_points(points):
    if not points:
        return DUBLIN_CENTER
    return (
        sum(p["lat"] for p in points) / len(points),
        sum(p["lon"] for p in points) / len(points),
    )


def build_html(center, points):
    c25 = sum(1 for p in points if p["dublin_district"] == 25)
    c26 = sum(1 for p in points if p["dublin_district"] == 26)
    c27 = sum(1 for p in points if p["dublin_district"] == 27)
    c_other = len(points) - c25 - c26 - c27
    payload = {
        "center": {"lat": center[0], "lng": center[1]},
        "points": points,
        "reference_point": {"lat": REFERENCE_POINT[0], "lng": REFERENCE_POINT[1]},
        "stats": {"d25": c25, "d26": c26, "d27": c27, "other": c_other},
    }
    data_json = json.dumps(payload, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="en"><head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Rematch districts map (OpenStreetMap)</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    html, body, #map {{ height: 100%; margin: 0; padding: 0; font-family: Arial, sans-serif; }}
    .panel {{ position: absolute; top: 12px; left: 12px; z-index: 1000; background: #fff; border: 1px solid #ccc; border-radius: 8px; padding: 10px 12px; font-size: 13px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); line-height: 1.5; }}
    .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }}
  </style>
</head><body>
  <div class="panel" id="summary"></div>
  <div id="map"></div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const DATA = {data_json};
    const map = L.map('map').setView([DATA.center.lat, DATA.center.lng], 11);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }}).addTo(map);
    const ref = DATA.reference_point;
    L.polyline([[ref.lat, ref.lng], [ref.lat, 180]], {{ color: '#2e7d32', weight: 3, opacity: 0.95 }}).addTo(map);
    L.polyline([[-90, ref.lng], [90, ref.lng]], {{ color: '#6a1b9a', weight: 3, opacity: 0.85, dashArray: '8,6' }}).addTo(map);
    L.circleMarker([ref.lat, ref.lng], {{ radius: 6, color: '#111', weight: 1.5, fillColor: '#ffeb3b', fillOpacity: 1 }}).addTo(map);
    for (const item of DATA.points) {{
      L.circleMarker([item.lat, item.lon], {{ radius: 5, color: '#222', weight: 1, fillColor: item.color, fillOpacity: 0.9 }}).addTo(map);
    }}
    document.getElementById('summary').innerHTML = `
      <div><span class="dot" style="background:{COLOR_25}"></span>25（直线左侧）: <b>${{DATA.stats.d25}}</b></div>
      <div><span class="dot" style="background:{COLOR_26}"></span>26（右侧且射线上方）: <b>${{DATA.stats.d26}}</b></div>
      <div><span class="dot" style="background:{COLOR_27}"></span>27（右侧且射线下方）: <b>${{DATA.stats.d27}}</b></div>
      <div><span class="dot" style="background:{COLOR_OTHER}"></span>其他区号: <b>${{DATA.stats.other}}</b></div>
      <div>总计 (Dublin 且有坐标): <b>${{DATA.points.length}}</b></div>
    `;
  </script>
</body></html>"""


def main():
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    input_path = Path(args.input)
    output_path = Path(args.output)
    if not input_path.is_absolute():
        input_path = script_dir / input_path
    if not output_path.is_absolute():
        output_path = script_dir / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    points = load_dublin_points(input_path)
    center = center_for_points(points)
    output_path.write_text(build_html(center, points), encoding="utf-8")
    print(f"Saved map HTML: {output_path}")
    print(f"Dublin points={len(points)}")


if __name__ == "__main__":
    main()

