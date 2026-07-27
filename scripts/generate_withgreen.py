#!/usr/bin/env python3
"""Generate the independent WithGreen location snapshot."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
from pathlib import Path

from location_data_common import (
    TARGET_AREAS,
    area_for_address,
    build_dataset,
    clean_text,
    fetch_text,
    finish,
    location,
    number,
)


SOURCE_URL = "https://store.withgreen.club/"
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
WEEKDAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")


def directions_url(item: dict[str, object]) -> str:
    wrapper = item.get("inputUrlWithModal")
    if not isinstance(wrapper, dict):
        return ""
    payload = wrapper.get("inputUrlWithModal")
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return ""
    for candidate in payload["items"]:
        if isinstance(candidate, dict) and clean_text(candidate.get("url")):
            return clean_text(candidate["url"])
    return ""


def format_time(value: object) -> str:
    return clean_text(value)[:5]


def hours(item: dict[str, object]) -> str:
    raw = item.get("businessHours")
    if not isinstance(raw, list):
        return ""
    by_day = {
        clean_text(row.get("name")): (format_time(row.get("openTime")), format_time(row.get("closeTime")))
        for row in raw
        if isinstance(row, dict)
    }
    ordered = [by_day[day] for day in WEEKDAYS if by_day.get(day)]
    if not ordered:
        return ""
    if len(set(ordered)) == 1:
        return f"Daily {ordered[0][0]}-{ordered[0][1]}"
    weekdays = [by_day[day] for day in WEEKDAYS[:5] if by_day.get(day)]
    weekend = [by_day[day] for day in WEEKDAYS[5:] if by_day.get(day)]
    if weekdays and weekend and len(set(weekdays)) == 1 and len(set(weekend)) == 1:
        return f"Weekdays {weekdays[0][0]}-{weekdays[0][1]}; Weekend {weekend[0][0]}-{weekend[0][1]}"
    return "Hours vary"


def generate(timeout: float) -> dict[str, object]:
    locations: list[dict[str, object]] = []
    skipped: list[dict[str, str]] = []
    for requested_area in TARGET_AREAS:
        url = f"{SOURCE_URL}{urllib.parse.quote(requested_area)}/"
        try:
            html = fetch_text(url, timeout=timeout, accept="text/html,application/xhtml+xml")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                skipped.append({"area": requested_area, "url": url, "reason": "not listed"})
                continue
            raise
        match = NEXT_DATA_RE.search(html)
        if not match:
            raise ValueError(f"WithGreen page did not contain __NEXT_DATA__: {url}")
        data = json.loads(match.group(1))
        shops = data.get("props", {}).get("pageProps", {}).get("shopsData", {}).get("shops")
        if not isinstance(shops, list):
            raise ValueError(f"WithGreen page did not contain a shops list: {url}")
        for item in shops:
            if not isinstance(item, dict):
                continue
            address = clean_text(item.get("address"))
            area = area_for_address(address) or requested_area
            lat = number(item.get("latitude"))
            lng = number(item.get("longitude"))
            if area not in TARGET_AREAS or lat is None or lng is None:
                continue
            identity = clean_text(item.get("storeId") or item.get("id")) or f"{lat:.7f}-{lng:.7f}"
            locations.append(
                location(
                    location_id=f"withgreen-{identity}",
                    brand="WithGreen",
                    short="WG",
                    name=clean_text(item.get("nameKanji")) or "WithGreen",
                    address=address,
                    lat=lat,
                    lng=lng,
                    area=area,
                    status=clean_text(item.get("businessStatus")) or "Unknown",
                    hours=hours(item),
                    phone=clean_text(item.get("phoneNumber")),
                    postal_code=clean_text(item.get("postalCode")),
                    url=url,
                    directions_url=directions_url(item),
                )
            )
    return build_dataset(
        source_id="withgreen",
        source_name="WithGreen",
        source_url=SOURCE_URL,
        locations=locations,
        minimum_count=25,
        source_notes={"skippedAreas": skipped},
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/withgreen.json")
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args(argv)
    try:
        return finish(Path(args.output), generate(args.timeout))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"WithGreen generation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
