#!/usr/bin/env python3
"""Download and normalize the Tokyo Bike Share port map for static hosting."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


MAP_ID = "1L2l1EnQJhCNlm_Xxkp9RTjIj68Q"
SOURCE_URL = f"https://www.google.com/maps/d/viewer?mid={MAP_ID}"
KML_URL = f"https://www.google.com/maps/d/kml?mid={MAP_ID}&forcekml=1"


def clean_text(value: str | None) -> str:
    return " ".join((value or "").split())


def fetch_kml(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.google-earth.kml+xml,application/xml,*/*",
            "User-Agent": "RunPlannerDataUpdater/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def valid_coordinate(lat: float, lng: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lng <= 180


def parse_ports(kml: bytes) -> list[dict[str, object]]:
    root = ET.fromstring(kml)
    ports: list[dict[str, object]] = []
    seen: set[str] = set()

    for placemark in root.findall(".//{*}Placemark"):
        name = clean_text(placemark.findtext("{*}name"))
        coordinates = placemark.findtext(".//{*}Point/{*}coordinates")
        if not name or not coordinates:
            continue
        first_coordinate = coordinates.strip().split()[0]
        parts = first_coordinate.split(",")
        if len(parts) < 2:
            continue
        try:
            lng = float(parts[0])
            lat = float(parts[1])
        except ValueError:
            continue
        if not valid_coordinate(lat, lng):
            continue

        identity = f"{name}\0{lat:.7f}\0{lng:.7f}".encode()
        port_id = hashlib.sha1(identity).hexdigest()[:12]
        if port_id in seen:
            continue
        seen.add(port_id)
        ports.append(
            {
                "id": port_id,
                "name": name,
                "lat": round(lat, 7),
                "lng": round(lng, 7),
            }
        )

    ports.sort(key=lambda item: (str(item["name"]), str(item["id"])))
    return ports


def build_dataset(kml: bytes) -> dict[str, object]:
    ports = parse_ports(kml)
    if not ports:
        raise ValueError("the KML did not contain any point placemarks")
    latitudes = [float(port["lat"]) for port in ports]
    longitudes = [float(port["lng"]) for port in ports]
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": SOURCE_URL,
        "sourceName": "Tokyo Bike Share Station Map",
        "counts": {"total": len(ports)},
        "bounds": {
            "south": min(latitudes),
            "west": min(longitudes),
            "north": max(latitudes),
            "east": max(longitudes),
        },
        "ports": ports,
    }


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="docomo-cycle-ports.json", help="output JSON path")
    parser.add_argument("--input", help="read an existing KML file instead of downloading it")
    parser.add_argument("--url", default=KML_URL, help="KML download URL")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        kml = Path(args.input).read_bytes() if args.input else fetch_kml(args.url)
        dataset = build_dataset(kml)
        write_json(Path(args.output), dataset)
    except (OSError, ET.ParseError, ValueError) as error:
        print(f"cycle-port download failed: {error}", file=sys.stderr)
        return 1
    print(f"wrote {args.output} with {dataset['counts']['total']} ports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
