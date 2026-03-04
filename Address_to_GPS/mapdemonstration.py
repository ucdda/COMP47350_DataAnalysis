#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


DEFAULT_CENTER = (53.425, -7.944)  # Ireland approx center
SUCCESS_STATUSES = {"ok", "ok_relaxed_area"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render geocoding results on OpenStreetMap (success=red, failure=gray)."
    )
    parser.add_argument(
        "--input",
        default="COMP47350_DataAnalysis/Address_to_GPS/ppr-group-25208508-train-lab3-preview-geocoded-1000.csv",
        help="Input geocoded CSV path.",
    )
    parser.add_argument(
        "--output",
        default="COMP47350_DataAnalysis/Address_to_GPS/geocode_map_demo_osm.html",
        help="Output HTML path.",
    )
    return parser.parse_args()


def to_float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def county_centroids(success_rows):
    buckets = {}
    for row in success_rows:
        county = (row.get("County") or "").strip()
        lat = to_float_or_none(row.get("latitude"))
        lon = to_float_or_none(row.get("longitude"))
        if not county or lat is None or lon is None:
            continue
        if county not in buckets:
            buckets[county] = {"lat_sum": 0.0, "lon_sum": 0.0, "n": 0}
        buckets[county]["lat_sum"] += lat
        buckets[county]["lon_sum"] += lon
        buckets[county]["n"] += 1

    centroids = {}
    for county, agg in buckets.items():
        centroids[county] = {
            "lat": agg["lat_sum"] / agg["n"],
            "lon": agg["lon_sum"] / agg["n"],
        }
    return centroids


def load_points(csv_path):
    success_points = []
    failed_points = []

    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    for row in rows:
        status = (row.get("geocode_status") or "").strip()
        lat = to_float_or_none(row.get("latitude"))
        lon = to_float_or_none(row.get("longitude"))
        item = {
            "address": row.get("Address", ""),
            "county": row.get("County", ""),
            "status": status,
            "query": row.get("geocode_query", ""),
            "lat": lat,
            "lon": lon,
        }
        if status in SUCCESS_STATUSES and lat is not None and lon is not None:
            success_points.append(item)
        else:
            failed_points.append(item)

    centroids = county_centroids(success_points)
    for item in failed_points:
        if item["lat"] is None or item["lon"] is None:
            county = (item["county"] or "").strip()
            c = centroids.get(county)
            if c:
                item["lat"] = c["lat"]
                item["lon"] = c["lon"]
            else:
                item["lat"], item["lon"] = DEFAULT_CENTER

    return success_points, failed_points


def build_html(center, success_points, failed_points):
    payload = {
        "center": {"lat": center[0], "lng": center[1]},
        "success": success_points,
        "failed": failed_points,
    }
    data_json = json.dumps(payload, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Geocode Map Demo (OpenStreetMap)</title>
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
    const map = L.map('map').setView([DATA.center.lat, DATA.center.lng], 7);

    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);

    function popupHtml(item) {{
      return `
        <div style="max-width:320px;">
          <b>Status:</b> ${{item.status}}<br/>
          <b>Address:</b> ${{item.address}}<br/>
          <b>County:</b> ${{item.county}}<br/>
          <b>Query:</b> ${{item.query}}<br/>
          <b>Lat/Lon:</b> ${{item.lat}}, ${{item.lon}}
        </div>
      `;
    }}

    function drawPoint(item, color) {{
      L.circleMarker([item.lat, item.lon], {{
        radius: 5,
        color: '#222',
        weight: 1,
        fillColor: color,
        fillOpacity: 0.9
      }}).addTo(map).bindPopup(popupHtml(item));
    }}

    for (const item of DATA.success) drawPoint(item, '#d32f2f');
    for (const item of DATA.failed) drawPoint(item, '#808080');

    const total = DATA.success.length + DATA.failed.length;
    const successRate = total ? ((DATA.success.length / total) * 100).toFixed(2) : '0.00';
    document.getElementById('summary').innerHTML = `
      <div><span class="dot" style="background:#d32f2f"></span>Success: <b>${{DATA.success.length}}</b></div>
      <div><span class="dot" style="background:#808080"></span>Failed: <b>${{DATA.failed.length}}</b></div>
      <div>Total: <b>${{total}}</b> | Success rate: <b>${{successRate}}%</b></div>
    `;
  </script>
</body>
</html>
"""


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    success_points, failed_points = load_points(input_path)
    html = build_html(DEFAULT_CENTER, success_points, failed_points)
    output_path.write_text(html, encoding="utf-8")

    total = len(success_points) + len(failed_points)
    success_rate = (len(success_points) / total * 100) if total else 0.0
    print(f"Saved map HTML: {output_path}")
    print(f"Success={len(success_points)} Failed={len(failed_points)} Total={total}")
    print(f"Success rate={success_rate:.2f}%")


if __name__ == "__main__":
    main()
