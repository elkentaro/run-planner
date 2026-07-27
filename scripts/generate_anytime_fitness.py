#!/usr/bin/env python3
"""Generate the independent Anytime Fitness location snapshot."""

from __future__ import annotations

import argparse
import sys
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


SOURCE_URL = "https://www.anytimefitness.co.jp/wp/wp-content/plugins/shoplist.php"


def absolute_url(value: object) -> str:
    text = clean_text(value)
    if not text or text == "/":
        return "https://www.anytimefitness.co.jp/"
    if text.startswith(("http://", "https://")):
        return text
    return f"https://www.anytimefitness.co.jp/{text.lstrip('/')}"


def generate(timeout: float) -> dict[str, object]:
    raw = fetch_json(SOURCE_URL, timeout=timeout)
    if not isinstance(raw, list):
        raise ValueError("Anytime source did not return a list")
    locations: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict) or item.get("isDeleted") or item.get("shouldBeExcludedFromMaps"):
            continue
        address = "".join(
            clean_text(item.get(field))
            for field in ("pref", "city", "address", "address2")
            if clean_text(item.get(field))
        )
        area = next((candidate for candidate in TARGET_AREAS if address.startswith(candidate)), None)
        lat = number(item.get("lat"))
        lng = number(item.get("lng"))
        if not area or lat is None or lng is None:
            continue
        differentiator = clean_text(item.get("differentiator"))
        name = (
            f"Anytime Fitness {differentiator}店"
            if differentiator
            else clean_text(item.get("name")) or "Anytime Fitness"
        )
        identity = clean_text(item.get("billingNumber") or item.get("linkurl")) or f"{lat:.7f}-{lng:.7f}"
        locations.append(
            location(
                location_id=f"anytime-{identity}",
                brand="Anytime Fitness",
                short="AF",
                name=name,
                address=address,
                lat=lat,
                lng=lng,
                area=area,
                status=clean_text(item.get("status")) or "Unknown",
                url=absolute_url(item.get("linkurl") or item.get("url")),
            )
        )
    return build_dataset(
        source_id="anytime-fitness",
        source_name="Anytime Fitness",
        source_url=SOURCE_URL,
        locations=locations,
        minimum_count=500,
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/anytime-fitness.json")
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args(argv)
    try:
        return finish(Path(args.output), generate(args.timeout))
    except (OSError, ValueError) as error:
        print(f"Anytime Fitness generation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
