#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


DUBLIN_CENTER = (53.35, -6.26)
SUCCESS_STATUSES = {"ok_nominatim", "ok_mapbox_strict", "ok_mapbox_relaxed"}
COLOR_DISTRICT_UNKNOWN = "#1976d2"  # blue: dublin_district == -1
COLOR_DISTRICT_KNOWN = "#d32f2f"  # red: otherwise


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render Dublin geocoded points: dublin_district=-1 blue, else red (County=Dublin only)."
    )
    parser.add_argument(
        "--input",
        default="districted-20260311-143854.csv",
        help="Input districted CSV (e.g. districted-YYYYMMDD-HHMMSS.csv).",
    )
    parser.add_argument(
        "--output",
        default="geocode_map_demo_osm.html",
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


def load_dublin_points(csv_path):
    """Only County=Dublin rows with successful geocode and coordinates; color by dublin_district."""
    points = []

    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

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
        color = COLOR_DISTRICT_UNKNOWN if d == -1 else COLOR_DISTRICT_KNOWN

        points.append(
            {
                "address": row.get("Address", ""),
                "county": row.get("County", ""),
                "status": status,
                "query": row.get("geocode_query", ""),
                "dublin_district": d,
                "lat": lat,
                "lon": lon,
                "color": color,
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
    n_blue = sum(1 for p in points if p["color"] == COLOR_DISTRICT_UNKNOWN)
    n_red = len(points) - n_blue

    payload = {
        "center": {"lat": center[0], "lng": center[1]},
        "points": points,
        "stats": {"blue": n_blue, "red": n_red},
    }
    data_json = json.dumps(payload, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Dublin districts map (OpenStreetMap)</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    html, body, #map {{
      height: 100%;
      margin: 0;
      padding: 0;
      font-family: Arial, sans-serif;
    }}
    .panel {{
      position: absolute;
      top: 12px;
      left: 12px;
      z-index: 1000;
      background: #fff;
      border: 1px solid #ccc;
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 13px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }}
    .dot {{
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      margin-right: 6px;
    }}
  </style>
</head>
<body>
  <div class="panel" id="summary"></div>
  <div id="map"></div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const DATA = {data_json};
    const map = L.map('map').setView([DATA.center.lat, DATA.center.lng], 11);

    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);

    function popupHtml(item) {{
      const dist = item.dublin_district === null || item.dublin_district === undefined
        ? '—' : String(item.dublin_district);
      return `
        <div style="max-width:320px;">
          <b>Status:</b> ${{item.status}}<br/>
          <b>Address:</b> ${{item.address}}<br/>
          <b>County:</b> ${{item.county}}<br/>
          <b>dublin_district:</b> ${{dist}}<br/>
          <b>Query:</b> ${{item.query}}<br/>
          <b>Lat/Lon:</b> ${{item.lat}}, ${{item.lon}}
        </div>
      `;
    }}

    function drawPoint(item) {{
      L.circleMarker([item.lat, item.lon], {{
        radius: 5,
        color: '#222',
        weight: 1,
        fillColor: item.color,
        fillOpacity: 0.9
      }}).addTo(map).bindPopup(popupHtml(item));
    }}

    for (const item of DATA.points) drawPoint(item);

    document.getElementById('summary').innerHTML = `
      <div><span class="dot" style="background:{COLOR_DISTRICT_UNKNOWN}"></span>dublin_district = -1: <b>${{DATA.stats.blue}}</b></div>
      <div><span class="dot" style="background:{COLOR_DISTRICT_KNOWN}"></span>其他: <b>${{DATA.stats.red}}</b></div>
      <div>总计 (Dublin 且有坐标): <b>${{DATA.points.length}}</b></div>
    `;
  </script>
</body>
</html>
"""


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
    html = build_html(center, points)
    output_path.write_text(html, encoding="utf-8")

    n_blue = sum(1 for p in points if p["color"] == COLOR_DISTRICT_UNKNOWN)
    print(f"Saved map HTML: {output_path}")
    print(f"Dublin points={len(points)} (blue dublin_district=-1: {n_blue}, red otherwise: {len(points) - n_blue})")


if __name__ == "__main__":
    main()
