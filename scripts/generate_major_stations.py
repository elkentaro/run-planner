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
    stations = raw.get("stations") if isinstance(raw, dict) else None
    if not isinstance(stations, list) or len(stations) < 80:
        raise ValueError("major-station source did not contain at least 80 stations")
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
            "id": "major-stations",
            "name": "Open Portal station passenger rankings",
            "type": "curated",
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
