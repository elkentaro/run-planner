#!/usr/bin/env python3
"""Generate a static Kanto and Yamanashi mountain-peak snapshot from GSI data."""

from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from location_data_common import fetch_bytes, write_json_if_changed


DEFAULT_SOURCE_URL = "https://web1.gsi.go.jp/KOKUJYOHO/MOUNTAIN/1003zan20260331.zip"
TARGET_PREFECTURES = {
    "茨城県",
    "栃木県",
    "群馬県",
    "埼玉県",
    "千葉県",
    "東京都",
    "神奈川県",
    "山梨県",
}


def generate(source_url: str) -> dict[str, object]:
    archive_bytes = fetch_bytes(source_url, accept="application/zip")
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        geojson_name = next(name for name in archive.namelist() if name.endswith(".geojson"))
        source = json.loads(archive.read(geojson_name))

    peaks: list[dict[str, object]] = []
    for feature in source.get("features", []):
        properties = feature.get("properties", {})
        prefectures = str(properties.get("都道府県") or "").split()
        if not TARGET_PREFECTURES.intersection(prefectures):
            continue
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            continue
        serial = int(properties["連番"])
        name = str(properties["山名＜山頂名＞"])
        peaks.append(
            {
                "id": f"gsi-peak-{serial}",
                "name": name,
                "nameJa": name,
                "nameReading": str(properties.get("山名よみ＜山頂名よみ＞") or ""),
                "lat": float(coordinates[1]),
                "lng": float(coordinates[0]),
                "elevation": int(properties["標高値(m)"]),
                "elevationType": str(properties.get("種別") or ""),
                "pref": " ".join(prefectures),
            }
        )
    peaks.sort(key=lambda item: (str(item["pref"]), -int(item["elevation"]), str(item["name"])))
    if not 100 <= len(peaks) <= 200:
        raise ValueError(f"expected 100-200 mountain peaks, received {len(peaks)}")
    return {
        "schemaVersion": 1,
        "source": {
            "id": "gsi-main-mountains",
            "name": "GSI Main Mountain Elevations of Japan",
            "url": source_url,
            "type": "official",
        },
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "counts": {"total": len(peaks)},
        "peaks": peaks,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--output", default="data/mountain-peaks.json")
    args = parser.parse_args(argv)
    try:
        payload = generate(args.source_url)
        changed = write_json_if_changed(Path(args.output), payload)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(f"mountain-peak generation failed: {error}", file=sys.stderr)
        return 1
    print(f"{'updated' if changed else 'unchanged'} {args.output} ({payload['counts']['total']} peaks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
