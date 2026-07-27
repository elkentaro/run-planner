#!/usr/bin/env python3
"""Generate the independent FamilyMart location snapshot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from location_data_common import (
    area_for_address,
    build_dataset,
    clean_text,
    fetch_json,
    finish,
    location,
    number,
)


SOURCE_URL = "https://store.family.co.jp/api/points"


def generate(timeout: float) -> dict[str, object]:
    raw = fetch_json(SOURCE_URL, timeout=timeout)
    items = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise ValueError("FamilyMart source did not return an items list")
    locations: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        address = clean_text(item.get("address"))
        area = area_for_address(address)
        lat = number(item.get("latitude"))
        lng = number(item.get("longitude"))
        if not area or lat is None or lng is None:
            continue
        extra = item.get("extra_fields") if isinstance(item.get("extra_fields"), dict) else {}
        identity = clean_text(item.get("key") or item.get("id")) or f"{lat:.7f}-{lng:.7f}"
        store_name = clean_text(item.get("name"))
        if "familymart" not in store_name.lower() and "ファミリーマート" not in store_name:
            store_name = f"FamilyMart {store_name}" if store_name else "FamilyMart"
        locations.append(
            location(
                location_id=f"familymart-{identity}",
                brand="FamilyMart",
                short="FM",
                name=store_name,
                address=address,
                lat=lat,
                lng=lng,
                area=area,
                status="Open" if clean_text(extra.get("PublicFlg")) == "1" else "",
                hours=clean_text(extra.get("I1")),
                phone=clean_text(extra.get("Tel")),
                postal_code=clean_text(extra.get("ZipCode")),
                url="https://store.family.co.jp/",
            )
        )
    return build_dataset(
        source_id="familymart",
        source_name="FamilyMart",
        source_url=SOURCE_URL,
        locations=locations,
        minimum_count=4000,
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/familymart.json")
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args(argv)
    try:
        return finish(Path(args.output), generate(args.timeout))
    except (OSError, ValueError) as error:
        print(f"FamilyMart generation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
