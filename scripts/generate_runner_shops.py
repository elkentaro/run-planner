#!/usr/bin/env python3
"""Generate the independent locally curated running-shop snapshot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from location_data_common import build_dataset, finish, read_json


def generate(source_path: Path) -> dict[str, object]:
    raw = read_json(source_path)
    locations = raw.get("locations") if isinstance(raw, dict) else None
    if not isinstance(locations, list):
        raise ValueError("runner-shop source did not contain a locations list")
    return build_dataset(
        source_id="runner-shops",
        source_name="Run Planner curated running shops",
        source_url="https://runpoya.com/shop-info/",
        locations=locations,
        minimum_count=1,
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="sources/runner-shops.json")
    parser.add_argument("--output", default="data/runner-shops.json")
    args = parser.parse_args(argv)
    try:
        return finish(Path(args.output), generate(Path(args.source)))
    except (OSError, ValueError) as error:
        print(f"running-shop generation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
