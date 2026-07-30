#!/usr/bin/env python3
"""Generate a static Kanagawa passenger-station snapshot from official MLIT data."""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.parse
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from location_data_common import fetch_bytes, write_json_if_changed


RAILWAY_URL = "https://nlftp.mlit.go.jp/ksj/gml/data/N02/N02-23/N02-23_GML.zip"
BOUNDARY_URL = "https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2026/N03-20260101_14_GML.zip"
OVERPASS_URL = "https://overpass.kumi.systems/api/interpreter"
OVERPASS_QUERY = """[out:json][timeout:180];
area["name"="神奈川県"]["boundary"="administrative"]["admin_level"="4"]->.searchArea;
nwr["railway"="station"]["name"](area.searchArea);
out center tags;"""
MAJOR_STATIONS = {
    "横浜",
    "川崎",
    "武蔵小杉",
    "新横浜",
    "藤沢",
    "大船",
    "鎌倉",
    "小田原",
    "箱根湯本",
    "強羅",
    "海老名",
    "本厚木",
    "相模大野",
    "橋本",
    "中央林間",
    "大和",
    "湘南台",
    "戸塚",
    "菊名",
    "日吉",
    "長津田",
    "あざみ野",
    "登戸",
    "溝の口",
    "桜木町",
    "関内",
    "上大岡",
    "金沢八景",
    "秦野",
    "伊勢原",
    "新松田",
    "山北",
}


def inside_ring(point: tuple[float, float], ring: list[list[float]]) -> bool:
    x, y = point
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing:
                inside = not inside
        previous = current
    return inside


def inside_geometry(point: tuple[float, float], geometry: dict[str, object]) -> bool:
    coordinates = geometry.get("coordinates", [])
    polygons = [coordinates] if geometry.get("type") == "Polygon" else coordinates
    if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        return False
    return any(
        inside_ring(point, polygon[0])
        and not any(inside_ring(point, hole) for hole in polygon[1:])
        for polygon in polygons
    )


def zip_json(data: bytes, suffix: str) -> dict[str, object]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        matches = [name for name in archive.namelist() if name.endswith(suffix)]
        name = next((name for name in matches if "UTF-8/" in name), matches[0])
        return json.loads(archive.read(name))


def english_names(endpoint: str) -> dict[str, str]:
    body = urllib.parse.urlencode({"data": OVERPASS_QUERY}).encode("utf-8")
    response = fetch_bytes(
        endpoint,
        timeout=240,
        accept="application/json",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=body,
    )
    data = json.loads(response)
    names: dict[str, str] = {}
    for element in data.get("elements", []):
        tags = element.get("tags", {})
        name = str(tags.get("name") or "")
        name_en = str(tags.get("name:en") or "")
        if name and name_en:
            names.setdefault(name, name_en)
    return names


def generate(railway_url: str, boundary_url: str, overpass_url: str) -> dict[str, object]:
    railway = zip_json(fetch_bytes(railway_url, accept="application/zip"), "_Station.geojson")
    boundary = zip_json(fetch_bytes(boundary_url, accept="application/zip"), ".geojson")
    boundaries = [feature["geometry"] for feature in boundary.get("features", [])]
    names_en = english_names(overpass_url)

    grouped: dict[str, list[tuple[dict[str, object], tuple[float, float]]]] = defaultdict(list)
    for feature in railway.get("features", []):
        geometry = feature.get("geometry", {})
        coordinates = geometry.get("coordinates", [])
        if geometry.get("type") != "LineString" or not coordinates:
            continue
        point = (
            sum(float(value[0]) for value in coordinates) / len(coordinates),
            sum(float(value[1]) for value in coordinates) / len(coordinates),
        )
        if not (138.9 <= point[0] <= 139.85 and 35.1 <= point[1] <= 35.7):
            continue
        if not any(inside_geometry(point, item) for item in boundaries):
            continue
        properties = feature.get("properties", {})
        grouped[str(properties["N02_005g"])].append((properties, point))

    stations: list[dict[str, object]] = []
    for group_id, records in grouped.items():
        names = {str(properties["N02_005"]) for properties, _ in records}
        if len(names) != 1:
            raise ValueError(f"station group {group_id} contains multiple names")
        name = next(iter(names))
        lines = sorted({str(properties["N02_003"]) for properties, _ in records})
        operators = sorted({str(properties["N02_004"]) for properties, _ in records})
        lng = sum(point[0] for _, point in records) / len(records)
        lat = sum(point[1] for _, point in records) / len(records)
        stations.append(
            {
                "id": f"kanagawa-mlit-{group_id}",
                "name": name,
                "nameJa": name,
                "nameEn": names_en.get(name, name),
                "lat": round(lat, 7),
                "lng": round(lng, 7),
                "pref": "神奈川県",
                "operator": " / ".join(operators),
                "lines": lines,
                "railTypes": sorted({str(properties["N02_001"]) for properties, _ in records}),
                "isMajor": name in MAJOR_STATIONS,
            }
        )
    stations.sort(key=lambda item: (str(item["nameJa"]), str(item["id"])))
    if not 330 <= len(stations) <= 380:
        raise ValueError(f"expected 330-380 Kanagawa stations, received {len(stations)}")
    return {
        "schemaVersion": 1,
        "source": {
            "id": "mlit-kanagawa-stations",
            "name": "MLIT National Land Numerical Information railway and administrative boundary data",
            "railwayUrl": railway_url,
            "boundaryUrl": boundary_url,
            "englishNames": "OpenStreetMap",
            "englishNamesUrl": overpass_url,
            "type": "official-with-osm-name-enrichment",
        },
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "total": len(stations),
            "major": sum(bool(item["isMajor"]) for item in stations),
        },
        "stations": stations,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--railway-url", default=RAILWAY_URL)
    parser.add_argument("--boundary-url", default=BOUNDARY_URL)
    parser.add_argument("--overpass-url", default=OVERPASS_URL)
    parser.add_argument("--output", default="data/kanagawa-stations.json")
    args = parser.parse_args(argv)
    try:
        payload = generate(args.railway_url, args.boundary_url, args.overpass_url)
        changed = write_json_if_changed(Path(args.output), payload)
    except (OSError, ValueError, KeyError, StopIteration, zipfile.BadZipFile, json.JSONDecodeError) as error:
        print(f"Kanagawa-station generation failed: {error}", file=sys.stderr)
        return 1
    print(f"{'updated' if changed else 'unchanged'} {args.output} ({payload['counts']['total']} stations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
