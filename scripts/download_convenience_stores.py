#!/usr/bin/env python3
"""Download and normalize convenience-store data for the static run planner."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path


SUPPORTED_AREAS = ("東京都", "神奈川県", "埼玉県", "千葉県", "栃木県")
FAMILYMART_URL = "https://store.family.co.jp/api/points"
SEVEN_ELEVEN_URL = "https://seven-eleven-ss-api.areamarker.com/v1/search-by-condition"
SEVEN_PREF_CODES = {
    "13": "東京都",
    "14": "神奈川県",
    "11": "埼玉県",
    "12": "千葉県",
    "09": "栃木県",
}
SEVEN_FIELDS = [
    "kyo_id",
    "name",
    "lat_en",
    "lon_en",
    "pre_code",
    "city_code",
    "addr_1",
    "zip_code",
]
JST = timezone(timedelta(hours=9))


def read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")


def fetch_json(url: str, *, headers: dict[str, str] | None = None, body: object | None = None) -> object:
    payload = None
    request_headers = {
        "Accept": "application/json,*/*",
        "User-Agent": "Mozilla/5.0",
    }
    if headers:
        request_headers.update(headers)
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=payload, headers=request_headers)
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def load_cached_or_fetch(
    cache_path: Path,
    *,
    offline: bool,
    url: str,
    headers: dict[str, str] | None = None,
    body: object | None = None,
) -> object:
    if offline:
        return read_json(cache_path)
    data = fetch_json(url, headers=headers, body=body)
    write_json(cache_path, data)
    return data


def area_for_address(address: str) -> str | None:
    for area in SUPPORTED_AREAS:
        if address.startswith(area):
            return area
    return None


def number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not (-90 <= result <= 180):
        return None
    return result


def directions_url(lat: float, lng: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={lat:.7f},{lng:.7f}"


def clean_text(value: object) -> str:
    return str(value or "").strip()


def familymart_name(name: str) -> str:
    if not name:
        return "FamilyMart"
    lowered = name.lower()
    if "familymart" in lowered or "ファミリーマート" in name:
        return name
    return f"FamilyMart {name}"


def normalize_familymart(raw: object) -> list[dict[str, object]]:
    items = raw.get("items", []) if isinstance(raw, dict) else []
    stores: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        address = clean_text(item.get("address"))
        area = area_for_address(address)
        if not area:
            continue
        lat = number(item.get("latitude"))
        lng = number(item.get("longitude"))
        if lat is None or lng is None:
            continue
        extra = item.get("extra_fields") if isinstance(item.get("extra_fields"), dict) else {}
        key = clean_text(item.get("key") or item.get("id"))
        store = {
            "id": f"familymart-{key or f'{lat:.7f}-{lng:.7f}'}",
            "brand": "FamilyMart",
            "short": "FM",
            "name": familymart_name(clean_text(item.get("name"))),
            "address": address,
            "lat": lat,
            "lng": lng,
            "area": area,
            "status": "Open" if clean_text(extra.get("PublicFlg")) == "1" else "",
            "hours": clean_text(extra.get("I1")),
            "note": "",
            "phone": clean_text(extra.get("Tel")),
            "postalCode": clean_text(extra.get("ZipCode")),
            "url": "https://store.family.co.jp/",
            "directionsUrl": directions_url(lat, lng),
        }
        stores.append(store)
    return stores


def seven_request_body(pref_code: str) -> dict[str, object]:
    current_hour = datetime.now(JST).strftime("%Y%m%d%H")
    return {
        "corp_id": "711map",
        "paging_mode": "search_after",
        "size": 5000,
        "sort": "+pre_code,+city_code,+kyo_id",
        "fields": SEVEN_FIELDS,
        "search_conditions": [
            {"field": "col_10", "value": "1", "comparison_operator": "="},
            {"field": "col_2", "value": current_hour, "comparison_operator": "<="},
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
            {"field": "pre_code", "value": pref_code, "comparison_operator": "="},
        ],
    }


def normalize_seven_eleven(raw: object, pref_code: str) -> list[dict[str, object]]:
    area = SEVEN_PREF_CODES[pref_code]
    hits = []
    if isinstance(raw, dict):
        hits = raw.get("result", {}).get("hits", {}).get("hit", [])
    stores: list[dict[str, object]] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        fields = hit.get("fields") if isinstance(hit.get("fields"), dict) else {}
        lat = number(fields.get("lat_en"))
        lng = number(fields.get("lon_en"))
        if lat is None or lng is None:
            continue
        kyo_id = clean_text(fields.get("kyo_id") or hit.get("id"))
        store_name = clean_text(fields.get("name"))
        stores.append(
            {
                "id": f"seven-{kyo_id or f'{lat:.7f}-{lng:.7f}'}",
                "brand": "7-Eleven",
                "short": "7/11",
                "name": f"7-Eleven {store_name}" if store_name else "7-Eleven",
                "address": clean_text(fields.get("addr_1")),
                "lat": lat,
                "lng": lng,
                "area": area,
                "status": "Open",
                "hours": "",
                "note": "",
                "phone": "",
                "postalCode": clean_text(fields.get("zip_code")),
                "url": "https://seven-eleven.areamarker.com/711map/top",
                "directionsUrl": directions_url(lat, lng),
            }
        )
    return stores


def dedupe(stores: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    unique: list[dict[str, object]] = []
    for store in stores:
        key = clean_text(store.get("id"))
        fallback = f"{store.get('brand')}:{float(store['lat']):.7f}:{float(store['lng']):.7f}"
        marker = key or fallback
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(store)
    return unique


def build_dataset(cache_dir: Path, *, offline: bool) -> dict[str, object]:
    family_raw = load_cached_or_fetch(
        cache_dir / "family_all.json",
        offline=offline,
        url=FAMILYMART_URL,
    )
    stores = normalize_familymart(family_raw)

    seven_headers = {
        "Origin": "https://seven-eleven.areamarker.com",
        "Referer": "https://seven-eleven.areamarker.com/711map/top",
        "X-Amss-Shopsite-Corp-ID": "711map",
    }
    for pref_code in SEVEN_PREF_CODES:
        raw = load_cached_or_fetch(
            cache_dir / f"seven_{pref_code}.json",
            offline=offline,
            url=SEVEN_ELEVEN_URL,
            headers=seven_headers,
            body=seven_request_body(pref_code),
        )
        stores.extend(normalize_seven_eleven(raw, pref_code))

    stores = dedupe(stores)
    stores.sort(key=lambda item: (str(item["area"]), str(item["brand"]), str(item["name"]), str(item["id"])))
    by_brand = Counter(str(store["brand"]) for store in stores)
    by_area = Counter(str(store["area"]) for store in stores)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "areas": list(SUPPORTED_AREAS),
        "sources": {
            "familymart": FAMILYMART_URL,
            "sevenEleven": "https://seven-eleven.areamarker.com/711map/top",
        },
        "sourceNotes": {
            "lawson": "Skipped for now; no reliable downloader source is wired in yet."
        },
        "counts": {
            "total": len(stores),
            "byBrand": dict(sorted(by_brand.items())),
            "byArea": {area: by_area.get(area, 0) for area in SUPPORTED_AREAS},
        },
        "stores": stores,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="convenience-stores.json", help="output JSON path")
    parser.add_argument(
        "--cache-dir",
        default=".cache/convenience-stores",
        help="directory for raw downloader responses",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="read raw responses from --cache-dir without network requests",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    cache_dir = Path(args.cache_dir)
    output = Path(args.output)
    try:
        dataset = build_dataset(cache_dir, offline=args.offline)
    except FileNotFoundError as error:
        print(f"missing cached response: {error.filename}", file=sys.stderr)
        return 1
    write_json(output, dataset)
    print(
        f"wrote {output} with {dataset['counts']['total']} stores "
        f"({', '.join(f'{brand}: {count}' for brand, count in dataset['counts']['byBrand'].items())})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
