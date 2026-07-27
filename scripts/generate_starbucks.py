#!/usr/bin/env python3
"""Generate the independent Starbucks location snapshot."""

from __future__ import annotations

import argparse
import sys
import urllib.parse
from pathlib import Path

from location_data_common import (
    TARGET_AREAS,
    build_dataset,
    clean_text,
    fetch_json,
    finish,
    location,
    number,
)


SOURCE_PAGE = "https://store.starbucks.co.jp/"
API_URL = "https://hn8madehag.execute-api.ap-northeast-1.amazonaws.com/prd-2019-08-21/storesearch"
PREFECTURE_CODES = {"栃木県": "9", "埼玉県": "11", "千葉県": "12", "東京都": "13", "神奈川県": "14"}
DAY_FIELDS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def coordinates(value: object) -> tuple[float, float] | None:
    parts = clean_text(value).split(",")
    if len(parts) != 2:
        return None
    lat = number(parts[0])
    lng = number(parts[1])
    if lat is None or lng is None:
        return None
    return lat, lng


def hours(fields: dict[str, object]) -> str:
    ranges = []
    for day in DAY_FIELDS:
        start = clean_text(fields.get(f"{day}_open"))
        end = clean_text(fields.get(f"{day}_close"))
        if start and end:
            ranges.append(f"{start}-{end}")
    if len(ranges) == len(DAY_FIELDS) and len(set(ranges)) == 1:
        return f"Daily {ranges[0]}"
    weekday = ranges[:5]
    weekend = ranges[5:]
    if len(weekday) == 5 and len(weekend) == 2 and len(set(weekday)) == 1 and len(set(weekend)) == 1:
        return f"Weekdays {weekday[0]}; Weekend {weekend[0]}"
    return "Hours vary" if ranges else ""


def generate(timeout: float) -> dict[str, object]:
    pref_query = " ".join(f"pref_code:{code}" for code in PREFECTURE_CODES.values())
    base_params = {
        "size": "100",
        "q.parser": "structured",
        "q": f"(and ver:10000 record_type:1 (or {pref_query}))",
        "fq": "(and data_type:'prd')",
        "sort": "pref_code asc,store_id asc",
    }
    headers = {
        "Origin": "https://store.starbucks.co.jp",
        "Referer": SOURCE_PAGE,
        "User-Agent": "Mozilla/5.0",
    }
    hits: list[dict[str, object]] = []
    expected_total: int | None = None
    offset = 0
    while expected_total is None or len(hits) < expected_total:
        params = {**base_params, "start": str(offset)}
        url = f"{API_URL}?{urllib.parse.urlencode(params)}"
        raw = fetch_json(url, timeout=timeout, headers=headers)
        response_hits = raw.get("hits") if isinstance(raw, dict) else None
        page = response_hits.get("hit") if isinstance(response_hits, dict) else None
        if not isinstance(page, list):
            raise ValueError("Starbucks source did not return a hits list")
        if expected_total is None:
            expected_total = int(response_hits.get("found", 0))
        if not page:
            break
        hits.extend(page)
        offset += len(page)
        if offset > 5000:
            raise ValueError("Starbucks pagination exceeded the expected result limit")
    if expected_total is None or len(hits) < expected_total:
        raise ValueError(f"Starbucks pagination stopped at {len(hits)} of {expected_total or 0} results")

    locations: list[dict[str, object]] = []
    for hit in hits:
        fields = hit.get("fields") if isinstance(hit, dict) and isinstance(hit.get("fields"), dict) else {}
        area = clean_text(fields.get("address_1"))
        point = coordinates(fields.get("location_jp") or fields.get("location"))
        store_id = clean_text(fields.get("store_id"))
        if area not in TARGET_AREAS or not point or not store_id:
            continue
        lat, lng = point
        store_name = clean_text(fields.get("name"))
        locations.append(
            location(
                location_id=f"starbucks-{store_id}",
                brand="Starbucks",
                short="SB",
                name=f"Starbucks {store_name}" if store_name else "Starbucks",
                address=clean_text(fields.get("address_5")),
                lat=lat,
                lng=lng,
                area=area,
                status="Open",
                hours=hours(fields),
                phone=clean_text(fields.get("telephone")),
                postal_code=clean_text(fields.get("zip_code")),
                url=f"https://store.starbucks.co.jp/detail-{store_id}/",
            )
        )
    return build_dataset(
        source_id="starbucks",
        source_name="Starbucks",
        source_url=SOURCE_PAGE,
        locations=locations,
        minimum_count=650,
        source_notes={"endpoint": API_URL},
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/starbucks.json")
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args(argv)
    try:
        return finish(Path(args.output), generate(args.timeout))
    except (OSError, ValueError) as error:
        print(f"Starbucks generation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
