#!/usr/bin/env python3
"""Generate the independent CRISP location snapshot."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from location_data_common import (
    area_for_address,
    build_dataset,
    clean_text,
    fetch_text,
    finish,
    location,
    number,
)


SOURCE_URL = "https://crisp.co.jp/location"
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def time_range(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    start = clean_text(value.get("start"))
    end = clean_text(value.get("end"))
    if not start or not end:
        return ""
    return "CLOSED" if start == "00:00" and end == "00:00" else f"{start}-{end}"


def hours(item: dict[str, object]) -> str:
    raw = item.get("openingHours")
    if not isinstance(raw, dict):
        return ""
    by_day = {day: time_range(raw.get(day)) for day in WEEKDAYS}
    ordered = [by_day[day] for day in WEEKDAYS if by_day[day]]
    if not ordered:
        return ""
    if len(set(ordered)) == 1:
        return "Closed" if ordered[0] == "CLOSED" else f"Daily {ordered[0]}"
    weekdays = [by_day[day] for day in WEEKDAYS[:5] if by_day[day]]
    weekend = [by_day[day] for day in WEEKDAYS[5:] if by_day[day]]
    if weekdays and weekend and len(set(weekdays)) == 1 and len(set(weekend)) == 1:
        return f"Weekdays {weekdays[0]}; Weekend {weekend[0]}"
    return "Hours vary"


def generate(timeout: float) -> dict[str, object]:
    html = fetch_text(SOURCE_URL, timeout=timeout, accept="text/html,application/xhtml+xml")
    match = NEXT_DATA_RE.search(html)
    if not match:
        raise ValueError("CRISP page did not contain __NEXT_DATA__")
    data = json.loads(match.group(1))
    shops = data.get("props", {}).get("pageProps", {}).get("shops")
    if not isinstance(shops, list):
        raise ValueError("CRISP page did not contain a shops list")
    locations: list[dict[str, object]] = []
    for item in shops:
        if not isinstance(item, dict):
            continue
        address = clean_text(item.get("address"))
        area = area_for_address(address)
        position = item.get("position") if isinstance(item.get("position"), dict) else {}
        lat = number(position.get("lat"))
        lng = number(position.get("lng"))
        if not area or lat is None or lng is None:
            continue
        store_name = clean_text(item.get("name"))
        identity = clean_text(item.get("id")) or f"{lat:.7f}-{lng:.7f}"
        locations.append(
            location(
                location_id=f"crisp-{identity}",
                brand="CRISP",
                short="CR",
                name=(
                    f"CRISP {store_name}"
                    if store_name and not store_name.upper().startswith("CRISP")
                    else store_name or "CRISP"
                ),
                address=address,
                lat=lat,
                lng=lng,
                area=area,
                hours=hours(item),
                note=clean_text(item.get("statusMessage")),
                phone=clean_text(item.get("tel")),
                postal_code=clean_text(item.get("postalCode")),
                url=SOURCE_URL,
                directions_url=clean_text(item.get("mapHref")),
            )
        )
    return build_dataset(
        source_id="crisp",
        source_name="CRISP",
        source_url=SOURCE_URL,
        locations=locations,
        minimum_count=40,
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/crisp.json")
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args(argv)
    try:
        return finish(Path(args.output), generate(args.timeout))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"CRISP generation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
