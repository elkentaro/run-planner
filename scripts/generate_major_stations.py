#!/usr/bin/env python3
"""Generate the independent locally curated major-station snapshot."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from location_data_common import clean_text, number, read_json, write_json_if_changed


def generate(source_path: Path) -> dict[str, object]:
    raw = read_json(source_path)
    base_stations = raw.get("stations") if isinstance(raw, dict) else None
    if not isinstance(base_stations, list) or len(base_stations) < 80:
        raise ValueError("major-station source did not contain at least 80 stations")
    source = raw.get("source")
    if not isinstance(source, dict):
        raise ValueError("major-station source metadata must be an object")
    base_major_count = number(raw.get("baseMajorCount"))
    if base_major_count is None or not base_major_count.is_integer() or not 1 <= base_major_count <= len(base_stations):
        raise ValueError("major-station source has an invalid base major count")
    stations = [dict(station) if isinstance(station, dict) else station for station in base_stations]
    for station in stations[: int(base_major_count)]:
        if isinstance(station, dict):
            station["isMajor"] = True
    stations_by_name = {
        clean_text(station.get("nameJa") or station.get("name")): station
        for station in stations
        if isinstance(station, dict)
    }
    corridors = raw.get("corridors", [])
    if not isinstance(corridors, list):
        raise ValueError("major-station corridors must be a list")
    for corridor in corridors:
        if not isinstance(corridor, dict):
            raise ValueError("major-station source contains a non-object corridor")
        corridor_id = clean_text(corridor.get("id"))
        corridor_stations = corridor.get("stations")
        if not corridor_id or not isinstance(corridor_stations, list):
            raise ValueError("major-station source contains an invalid corridor")
        major_station_names = corridor.get("majorStations", [])
        if not isinstance(major_station_names, list):
            raise ValueError(f"major-station corridor {corridor_id} has invalid major stations")
        major_station_names = {clean_text(name) for name in major_station_names}
        for corridor_station in corridor_stations:
            if not isinstance(corridor_station, dict):
                raise ValueError(f"major-station corridor {corridor_id} contains a non-object station")
            station_name = clean_text(corridor_station.get("nameJa") or corridor_station.get("name"))
            if not station_name:
                raise ValueError(f"major-station corridor {corridor_id} contains an unnamed station")
            station = stations_by_name.get(station_name)
            if station is None:
                station = dict(corridor_station)
                station.setdefault("name", station_name)
                station.setdefault("nameJa", station_name)
                stations.append(station)
                stations_by_name[station_name] = station
            if station_name in major_station_names:
                station["isMajor"] = True
            lines = station.setdefault("lines", [])
            if not isinstance(lines, list):
                raise ValueError(f"major-station {station_name} has invalid lines")
            if corridor_id not in lines:
                lines.append(corridor_id)
    if len(stations) < 160:
        raise ValueError("major-station source did not produce at least 160 unique stations")
    ids: set[str] = set()
    for station in stations:
        if not isinstance(station, dict):
            raise ValueError("major-station source contains a non-object station")
        station_id = clean_text(station.get("id"))
        lat = number(station.get("lat"))
        lng = number(station.get("lng"))
        if not station_id or station_id in ids or lat is None or lng is None:
            raise ValueError(f"major-station source contains an invalid station: {station_id or '<missing>'}")
        ids.add(station_id)
    return {
        "schemaVersion": 1,
        "source": {
            **source,
            "id": "major-stations",
        },
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "counts": {"total": len(stations)},
        "stations": stations,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="sources/major-stations.json")
    parser.add_argument("--output", default="data/major-stations.json")
    args = parser.parse_args(argv)
    try:
        payload = generate(Path(args.source))
        changed = write_json_if_changed(Path(args.output), payload)
    except (OSError, ValueError) as error:
        print(f"major-station generation failed: {error}", file=sys.stderr)
        return 1
    print(f"{'updated' if changed else 'unchanged'} {args.output} ({payload['counts']['total']} stations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
