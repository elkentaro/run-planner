#!/usr/bin/env python3
"""Generate a static HELLO CYCLING port snapshot for four Kanto prefectures."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from location_data_common import clean_text, fetch_bytes, write_json_if_changed


SOURCE_URL = "https://api-public.odpt.org/api/v4/gbfs/hellocycling/station_information.json"
CATALOG_URL = "https://ckan.odpt.org/en/dataset/c_bikeshare_gbfs-openstreet"
TARGET_PREFECTURES = ("東京都", "神奈川県", "埼玉県", "千葉県")
MINIMUM_COUNTS = {
    "東京都": 3500,
    "神奈川県": 2300,
    "埼玉県": 2100,
    "千葉県": 1400,
}


def prefecture_for_address(address: str) -> str | None:
    return next((prefecture for prefecture in TARGET_PREFECTURES if address.startswith(prefecture)), None)


def capacity(item: dict[str, object]) -> int:
    value = item.get("vehicle_capacity", item.get("capacity", 0))
    try:
        return max(0, int(float(str(value))))
    except (TypeError, ValueError):
        return 0


def build_dataset(payload: dict[str, object]) -> dict[str, object]:
    data = payload.get("data", {})
    source_stations = data.get("stations", []) if isinstance(data, dict) else []
    if not isinstance(source_stations, list):
        raise ValueError("GBFS data.stations is not a list")

    ports: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in source_stations:
        if not isinstance(item, dict):
            continue
        station_id = clean_text(item.get("station_id"))
        name = clean_text(item.get("name"))
        address = clean_text(item.get("address"))
        area = prefecture_for_address(address)
        if not station_id or not name or area is None or station_id in seen:
            continue
        try:
            lat = float(item["lat"])
            lng = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            continue
        rental_uris = item.get("rental_uris", {})
        service_url = clean_text(rental_uris.get("web")) if isinstance(rental_uris, dict) else ""
        seen.add(station_id)
        ports.append(
            {
                "id": f"hello-cycling-{station_id}",
                "stationId": station_id,
                "name": name,
                "address": address,
                "lat": round(lat, 7),
                "lng": round(lng, 7),
                "area": area,
                "capacity": capacity(item),
                "serviceUrl": service_url,
            }
        )

    ports.sort(key=lambda item: (str(item["area"]), str(item["name"]), str(item["id"])))
    by_area = Counter(str(item["area"]) for item in ports)
    for area, minimum in MINIMUM_COUNTS.items():
        if by_area[area] < minimum:
            raise ValueError(f"expected at least {minimum} ports in {area}, received {by_area[area]}")

    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": {
            "id": "hello-cycling-gbfs",
            "name": "HELLO CYCLING",
            "provider": "OpenStreet Corp. / Association for Open Data of Public Transportation",
            "url": SOURCE_URL,
            "catalogUrl": CATALOG_URL,
            "license": "CC BY 4.0, ODC BY 1.0, ODbL 1.0",
            "gbfsVersion": clean_text(payload.get("version")),
        },
        "counts": {
            "total": len(ports),
            "byArea": {area: by_area[area] for area in TARGET_PREFECTURES},
        },
        "ports": ports,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/hello-cycling.json")
    parser.add_argument("--input", help="read an existing GBFS JSON file instead of downloading it")
    parser.add_argument("--url", default=SOURCE_URL)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        raw = Path(args.input).read_bytes() if args.input else fetch_bytes(args.url)
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("GBFS root is not an object")
        dataset = build_dataset(payload)
        changed = write_json_if_changed(Path(args.output), dataset)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"HELLO CYCLING generation failed: {error}", file=sys.stderr)
        return 1
    state = "updated" if changed else "unchanged"
    print(f"{state} {args.output} ({dataset['counts']['total']} ports)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
