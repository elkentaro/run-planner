#!/usr/bin/env python3
"""Generate the independent 7-Eleven location snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from location_data_common import (
    build_dataset,
    clean_text,
    fetch_json,
    finish,
    location,
    number,
)


SOURCE_PAGE = "https://seven-eleven.areamarker.com/711map/top"
API_URL = "https://seven-eleven-ss-api.areamarker.com/v1/search-by-condition"
PREFECTURES = {"09": "栃木県", "11": "埼玉県", "12": "千葉県", "13": "東京都", "14": "神奈川県"}
FIELDS = ("kyo_id", "name", "lat_en", "lon_en", "pre_code", "city_code", "addr_1", "zip_code")


def request_body(prefecture_code: str) -> dict[str, object]:
    return {
        "corp_id": "711map",
        "paging_mode": "search_after",
        "size": 5000,
        "sort": "+pre_code,+city_code,+kyo_id",
        "fields": list(FIELDS),
        "search_conditions": [
            {"field": "col_10", "value": "1", "comparison_operator": "="},
            {
                "field": "col_2",
                "value": datetime.now().strftime("%Y%m%d%H"),
                "comparison_operator": "<=",
            },
            {
                "conditions": [
                    {"field": "col_2", "value": "1", "comparison_operator": "prefix"},
                    {
                        "field": "col_2",
                        "value": "2",
                        "comparison_operator": "prefix",
                        "logical_operator": "OR",
                    },
                ]
            },
            {"field": "pre_code", "value": prefecture_code, "comparison_operator": "="},
        ],
    }


def generate(timeout: float) -> dict[str, object]:
    locations: list[dict[str, object]] = []
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://seven-eleven.areamarker.com",
        "Referer": SOURCE_PAGE,
        "X-Amss-Shopsite-Corp-ID": "711map",
    }
    for prefecture_code, area in PREFECTURES.items():
        raw = fetch_json(
            API_URL,
            timeout=timeout,
            headers=headers,
            body=json.dumps(request_body(prefecture_code)).encode("utf-8"),
        )
        hits = raw.get("result", {}).get("hits", {}).get("hit") if isinstance(raw, dict) else None
        if not isinstance(hits, list):
            raise ValueError(f"7-Eleven source did not return hits for prefecture {prefecture_code}")
        for hit in hits:
            fields = hit.get("fields") if isinstance(hit, dict) and isinstance(hit.get("fields"), dict) else {}
            lat = number(fields.get("lat_en"))
            lng = number(fields.get("lon_en"))
            identity = clean_text(fields.get("kyo_id") or hit.get("id"))
            if lat is None or lng is None or not identity:
                continue
            name = clean_text(fields.get("name"))
            locations.append(
                location(
                    location_id=f"seven-{identity}",
                    brand="7-Eleven",
                    short="7/11",
                    name=f"7-Eleven {name}" if name else "7-Eleven",
                    address=clean_text(fields.get("addr_1")),
                    lat=lat,
                    lng=lng,
                    area=area,
                    status="Open",
                    postal_code=clean_text(fields.get("zip_code")),
                    url=SOURCE_PAGE,
                )
            )
    return build_dataset(
        source_id="seven-eleven",
        source_name="7-Eleven",
        source_url=SOURCE_PAGE,
        locations=locations,
        minimum_count=6000,
        source_notes={"endpoint": API_URL},
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/seven-eleven.json")
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args(argv)
    try:
        return finish(Path(args.output), generate(args.timeout))
    except (OSError, ValueError) as error:
        print(f"7-Eleven generation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
