"""Shared helpers for independent static location-data generators."""

from __future__ import annotations

import json
import os
import tempfile
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TARGET_AREAS = ("東京都", "神奈川県", "埼玉県", "千葉県", "栃木県")
LOCATION_FIELDS = (
    "id",
    "brand",
    "short",
    "name",
    "address",
    "lat",
    "lng",
    "area",
    "status",
    "hours",
    "note",
    "phone",
    "postalCode",
    "url",
    "directionsUrl",
)


def clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def number(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def area_for_address(address: str) -> str | None:
    return next((area for area in TARGET_AREAS if address.startswith(area)), None)


def map_search_url(lat: float, lng: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={lat:.7f},{lng:.7f}"


def location(
    *,
    location_id: str,
    brand: str,
    short: str,
    name: str,
    address: str,
    lat: float,
    lng: float,
    area: str,
    status: str = "",
    hours: str = "",
    note: str = "",
    phone: str = "",
    postal_code: str = "",
    url: str = "",
    directions_url: str = "",
) -> dict[str, object]:
    return {
        "id": clean_text(location_id),
        "brand": clean_text(brand),
        "short": clean_text(short),
        "name": clean_text(name),
        "address": clean_text(address),
        "lat": float(lat),
        "lng": float(lng),
        "area": clean_text(area),
        "status": clean_text(status),
        "hours": clean_text(hours),
        "note": clean_text(note),
        "phone": clean_text(phone),
        "postalCode": clean_text(postal_code),
        "url": clean_text(url),
        "directionsUrl": clean_text(directions_url) or map_search_url(lat, lng),
    }


def fetch_bytes(
    url: str,
    *,
    timeout: float = 60,
    accept: str = "application/json,*/*",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> bytes:
    request_headers = {
        "Accept": accept,
        "User-Agent": "RunPlannerLocationUpdater/1.0 (https://github.com/elkentaro/run-planner)",
    }
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=request_headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_text(url: str, **kwargs: Any) -> str:
    return fetch_bytes(url, **kwargs).decode("utf-8")


def fetch_json(url: str, **kwargs: Any) -> object:
    return json.loads(fetch_text(url, **kwargs))


def sorted_unique(locations: list[dict[str, object]]) -> list[dict[str, object]]:
    unique: dict[str, dict[str, object]] = {}
    for item in locations:
        location_id = clean_text(item.get("id"))
        if not location_id:
            raise ValueError("location is missing an id")
        unique.setdefault(location_id, item)
    return sorted(
        unique.values(),
        key=lambda item: (
            clean_text(item.get("area")),
            clean_text(item.get("name")),
            clean_text(item.get("id")),
        ),
    )


def validate_locations(locations: list[dict[str, object]], *, minimum_count: int) -> None:
    if len(locations) < minimum_count:
        raise ValueError(f"expected at least {minimum_count} locations, received {len(locations)}")
    ids: set[str] = set()
    for index, item in enumerate(locations):
        missing = [field for field in LOCATION_FIELDS if field not in item]
        if missing:
            raise ValueError(f"location {index} is missing fields: {', '.join(missing)}")
        location_id = clean_text(item["id"])
        if not location_id or location_id in ids:
            raise ValueError(f"location {index} has a missing or duplicate id")
        ids.add(location_id)
        lat = number(item["lat"])
        lng = number(item["lng"])
        if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError(f"location {location_id} has invalid coordinates")
        if clean_text(item["area"]) not in TARGET_AREAS:
            raise ValueError(f"location {location_id} has an unsupported area")


def build_dataset(
    *,
    source_id: str,
    source_name: str,
    source_url: str,
    locations: list[dict[str, object]],
    minimum_count: int,
    source_notes: dict[str, object] | None = None,
) -> dict[str, object]:
    normalized = sorted_unique(locations)
    validate_locations(normalized, minimum_count=minimum_count)
    by_area = Counter(clean_text(item["area"]) for item in normalized)
    payload: dict[str, object] = {
        "schemaVersion": 1,
        "source": {
            "id": source_id,
            "name": source_name,
            "url": source_url,
        },
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "total": len(normalized),
            "byArea": {area: by_area.get(area, 0) for area in TARGET_AREAS},
        },
        "locations": normalized,
    }
    if source_notes:
        payload["sourceNotes"] = source_notes
    return payload


def read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def semantic_payload(payload: object) -> object:
    if not isinstance(payload, dict):
        return payload
    return {key: value for key, value in payload.items() if key != "generatedAt"}


def write_json_if_changed(path: Path, payload: dict[str, object]) -> bool:
    if path.exists():
        try:
            existing = read_json(path)
        except (OSError, json.JSONDecodeError):
            existing = None
        if semantic_payload(existing) == semantic_payload(payload):
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary_name, path)
        os.chmod(path, 0o644)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return True


def finish(output: Path, payload: dict[str, object]) -> int:
    changed = write_json_if_changed(output, payload)
    state = "updated" if changed else "unchanged"
    print(f"{state} {output} ({payload['counts']['total']} locations)")
    return 0
