#!/usr/bin/env python3
"""Download and normalize public-toilet data for the static run planner."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"
DEFAULT_BOUNDARY_ENDPOINT = "https://nominatim.openstreetmap.org/search"
DEFAULT_CACHE_DIR = ".cache/public-toilets"
DEFAULT_OUTPUT = "data/public-toilets.json"
USER_AGENT = "RunPlannerPublicToilets/1.0 (https://github.com/elkentaro/run-planner)"
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}
EXCLUDED_ACCESS = {"private", "customers", "no"}
AREA_NAMES = {
    "JP-13": "東京都",
    "JP-14": "神奈川県",
    "JP-11": "埼玉県",
    "JP-12": "千葉県",
    "JP-09": "栃木県",
}
AREA_REGIONS = {
    "JP-13": (
        ("mainland", (35.45, 138.90, 36.00, 140.05)),
        ("izu-north", (34.00, 139.00, 34.85, 139.70)),
        ("izu-south", (32.35, 139.35, 34.05, 140.00)),
        ("ogasawara", (26.50, 141.95, 27.20, 142.40)),
        ("iwo-jima", (24.70, 141.20, 24.85, 141.40)),
    ),
    "JP-14": (("main", (35.10, 138.85, 35.70, 139.85)),),
    "JP-11": (("main", (35.70, 138.65, 36.30, 139.95)),),
    "JP-12": (("main", (34.85, 139.70, 36.20, 141.00)),),
    "JP-09": (("main", (36.15, 139.30, 37.20, 140.35)),),
}
PUBLIC_TAGS = (
    "amenity",
    "name",
    "name:ja",
    "name:en",
    "access",
    "toilets:access",
    "opening_hours",
    "fee",
    "wheelchair",
    "changing_table",
    "unisex",
    "male",
    "female",
)


@dataclass(frozen=True)
class Tile:
    area_code: str
    region: str
    row: int
    column: int
    south: float
    west: float
    north: float
    east: float

    @property
    def key(self) -> str:
        return f"{self.region}-{self.row:03d}-{self.column:03d}"


class RequestPacer:
    def __init__(self, delay_seconds: float):
        self.delay_seconds = delay_seconds
        self.last_request_started: float | None = None

    def wait(self) -> None:
        if self.last_request_started is not None:
            remaining = self.delay_seconds - (time.monotonic() - self.last_request_started)
            if remaining > 0:
                print(f"waiting {remaining:.1f}s before the next Overpass request")
                time.sleep(remaining)
        self.last_request_started = time.monotonic()


def read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
    temporary.replace(path)


def semantic_dataset(data: object) -> object:
    if not isinstance(data, dict):
        return data
    normalized = {key: value for key, value in data.items() if key != "generatedAt"}
    source = normalized.get("source")
    if isinstance(source, dict):
        normalized["source"] = {key: value for key, value in source.items() if key != "timestamps"}
    return normalized


def build_query(tile: Tile, timeout_seconds: int) -> str:
    return f"""[out:json][timeout:{timeout_seconds}];
nwr["amenity"="toilets"]({tile.south:.6f},{tile.west:.6f},{tile.north:.6f},{tile.east:.6f});
out center;"""


def tiles_for_area(area_code: str, cell_size: float) -> list[Tile]:
    tiles: list[Tile] = []
    for region, (south, west, north, east) in AREA_REGIONS[area_code]:
        row = 0
        tile_south = south
        while tile_south < north:
            tile_north = min(north, tile_south + cell_size)
            column = 0
            tile_west = west
            while tile_west < east:
                tile_east = min(east, tile_west + cell_size)
                tiles.append(
                    Tile(
                        area_code=area_code,
                        region=region,
                        row=row,
                        column=column,
                        south=tile_south,
                        west=tile_west,
                        north=tile_north,
                        east=tile_east,
                    )
                )
                column += 1
                tile_west = tile_east
            row += 1
            tile_south = tile_north
    return tiles


def retry_after_seconds(error: urllib.error.HTTPError) -> float | None:
    value = error.headers.get("Retry-After", "").strip()
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            return None


def fetch_boundary(endpoint: str, area_code: str, *, request_timeout: int) -> object:
    query = urllib.parse.urlencode(
        {
            "q": f"{AREA_NAMES[area_code]},日本",
            "countrycodes": "jp",
            "format": "geojson",
            "polygon_geojson": "1",
            "polygon_threshold": "0.001",
            "limit": "1",
            "featureType": "state",
        }
    )
    request = urllib.request.Request(
        f"{endpoint}?{query}",
        headers={"Accept": "application/geo+json,application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=request_timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def validate_boundary(payload: object, area_code: str) -> dict[str, object]:
    if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
        raise ValueError(f"{area_code}: boundary response is not valid GeoJSON")
    features = payload["features"]
    if not features or not isinstance(features[0], dict):
        raise ValueError(f"{area_code}: boundary response has no matching prefecture")
    feature = features[0]
    properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
    geometry = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else {}
    if properties.get("osm_type") != "relation" or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"{area_code}: boundary response did not resolve to an OSM relation polygon")
    return payload


def load_boundary(
    area_code: str,
    cache_dir: Path,
    *,
    offline: bool,
    refresh: bool,
    endpoint: str,
    request_timeout: int,
    pacer: RequestPacer,
) -> dict[str, object]:
    cache_path = cache_dir / "boundaries" / f"{area_code}.geojson"
    if cache_path.exists() and not refresh:
        payload = validate_boundary(read_json(cache_path), area_code)
    else:
        if offline:
            raise FileNotFoundError(cache_path)
        pacer.wait()
        payload = validate_boundary(
            fetch_boundary(endpoint, area_code, request_timeout=request_timeout),
            area_code,
        )
        write_json(cache_path, payload)
    return payload["features"][0]["geometry"]


def ring_contains(ring: object, lng: float, lat: float) -> bool:
    if not isinstance(ring, list) or len(ring) < 4:
        return False
    inside = False
    previous = ring[-1]
    if not isinstance(previous, list) or len(previous) < 2:
        return False
    previous_x, previous_y = float(previous[0]), float(previous[1])
    for point in ring:
        if not isinstance(point, list) or len(point) < 2:
            continue
        x, y = float(point[0]), float(point[1])
        crosses = (y > lat) != (previous_y > lat)
        if crosses and lng < (previous_x - x) * (lat - y) / (previous_y - y) + x:
            inside = not inside
        previous_x, previous_y = x, y
    return inside


def polygon_contains(polygon: object, lng: float, lat: float) -> bool:
    if not isinstance(polygon, list) or not polygon:
        return False
    if not ring_contains(polygon[0], lng, lat):
        return False
    return not any(ring_contains(hole, lng, lat) for hole in polygon[1:])


def geometry_contains(geometry: dict[str, object], lng: float, lat: float) -> bool:
    coordinates = geometry.get("coordinates")
    if geometry.get("type") == "Polygon":
        return polygon_contains(coordinates, lng, lat)
    if geometry.get("type") == "MultiPolygon" and isinstance(coordinates, list):
        return any(polygon_contains(polygon, lng, lat) for polygon in coordinates)
    return False


def fetch_overpass(
    endpoint: str,
    query: str,
    *,
    request_timeout: int,
    retries: int,
    backoff_seconds: float,
) -> object:
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": USER_AGENT,
        },
    )
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=request_timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
                raise RuntimeError("Overpass returned an invalid JSON payload")
            if payload.get("remark"):
                raise RuntimeError(f"Overpass remark: {payload['remark']}")
            return payload
        except urllib.error.HTTPError as error:
            if error.code not in RETRYABLE_HTTP_CODES or attempt >= retries:
                raise
            delay = retry_after_seconds(error)
            if delay is None:
                delay = backoff_seconds * (2**attempt)
            print(
                f"Overpass HTTP {error.code}; retrying in {delay:.0f}s "
                f"({attempt + 1}/{retries})",
                file=sys.stderr,
            )
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, socket.timeout, RuntimeError) as error:
            if attempt >= retries:
                raise
            delay = backoff_seconds * (2**attempt)
            print(
                f"Overpass request failed: {error}; retrying in {delay:.0f}s "
                f"({attempt + 1}/{retries})",
                file=sys.stderr,
            )
            time.sleep(delay)
    raise RuntimeError("Overpass retry loop ended unexpectedly")


def clean_text(value: object) -> str:
    return str(value or "").strip()


def coordinate(value: object, *, latitude: bool) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    limit = 90 if latitude else 180
    return result if -limit <= result <= limit else None


def is_public(tags: dict[str, object]) -> bool:
    access = clean_text(tags.get("access") or tags.get("toilets:access")).lower()
    return not any(part.strip() in EXCLUDED_ACCESS for part in access.replace(";", ",").split(","))


def normalize_element(element: object, area_code: str) -> dict[str, object] | None:
    if not isinstance(element, dict):
        return None
    element_type = clean_text(element.get("type"))
    element_id = element.get("id")
    center = element.get("center") if isinstance(element.get("center"), dict) else {}
    lat = coordinate(element.get("lat", center.get("lat")), latitude=True)
    lng = coordinate(element.get("lon", center.get("lon")), latitude=False)
    tags = element.get("tags") if isinstance(element.get("tags"), dict) else {}
    if (
        element_type not in {"node", "way", "relation"}
        or not isinstance(element_id, int)
        or lat is None
        or lng is None
        or tags.get("amenity") != "toilets"
        or not is_public(tags)
    ):
        return None
    selected_tags = {
        key: clean_text(tags[key])
        for key in PUBLIC_TAGS
        if clean_text(tags.get(key))
    }
    return {
        "id": f"osm-{element_type}-{element_id}",
        "osmType": element_type,
        "osmId": element_id,
        "lat": lat,
        "lng": lng,
        "area": AREA_NAMES[area_code],
        "tags": selected_tags,
    }


def validate_raw_payload(payload: object, label: str) -> dict[str, object]:
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise ValueError(f"{label}: cached response is not a valid Overpass JSON payload")
    if payload.get("remark"):
        raise ValueError(f"{label}: cached response contains Overpass error: {payload['remark']}")
    return payload


def load_tile(
    tile: Tile,
    cache_dir: Path,
    *,
    offline: bool,
    refresh: bool,
    endpoint: str,
    query_timeout: int,
    request_timeout: int,
    retries: int,
    backoff_seconds: float,
    pacer: RequestPacer,
    cache_max_age_days: float,
) -> dict[str, object]:
    cache_path = cache_dir / tile.area_code / f"{tile.key}.json"
    cache_age_seconds = time.time() - cache_path.stat().st_mtime if cache_path.exists() else float("inf")
    cache_is_fresh = cache_age_seconds <= cache_max_age_days * 24 * 60 * 60
    if cache_path.exists() and (offline or (cache_is_fresh and not refresh)):
        return validate_raw_payload(read_json(cache_path), f"{tile.area_code}/{tile.key}")
    if offline:
        raise FileNotFoundError(cache_path)
    pacer.wait()
    query = build_query(tile, query_timeout)
    payload = validate_raw_payload(
        fetch_overpass(
            endpoint,
            query,
            request_timeout=request_timeout,
            retries=retries,
            backoff_seconds=backoff_seconds,
        ),
        f"{tile.area_code}/{tile.key}",
    )
    write_json(cache_path, payload)
    return payload


def build_dataset(
    area_codes: list[str],
    cache_dir: Path,
    *,
    offline: bool,
    refresh: bool,
    endpoint: str,
    query_timeout: int,
    request_timeout: int,
    retries: int,
    backoff_seconds: float,
    delay_seconds: float,
    cell_size: float,
    boundary_endpoint: str,
    refresh_boundaries: bool,
    cache_max_age_days: float,
) -> dict[str, object]:
    toilets_by_id: dict[str, dict[str, object]] = {}
    source_timestamps: dict[str, str] = {}
    pacer = RequestPacer(delay_seconds)
    boundary_pacer = RequestPacer(1.1)
    for area_code in area_codes:
        print(f"{area_code} {AREA_NAMES[area_code]}: loading boundary")
        boundary = load_boundary(
            area_code,
            cache_dir.parent,
            offline=offline,
            refresh=refresh_boundaries,
            endpoint=boundary_endpoint,
            request_timeout=request_timeout,
            pacer=boundary_pacer,
        )
        tiles = tiles_for_area(area_code, cell_size)
        print(f"{area_code} {AREA_NAMES[area_code]}: {len(tiles)} grid cells")
        accepted = 0
        timestamps: list[str] = []
        for index, tile in enumerate(tiles, start=1):
            print(f"{area_code} cell {index}/{len(tiles)} {tile.key}")
            raw = load_tile(
                tile,
                cache_dir,
                offline=offline,
                refresh=refresh,
                endpoint=endpoint,
                query_timeout=query_timeout,
                request_timeout=request_timeout,
                retries=retries,
                backoff_seconds=backoff_seconds,
                pacer=pacer,
                cache_max_age_days=cache_max_age_days,
            )
            osm3s = raw.get("osm3s") if isinstance(raw.get("osm3s"), dict) else {}
            timestamp = clean_text(osm3s.get("timestamp_osm_base"))
            if timestamp:
                timestamps.append(timestamp)
            for element in raw["elements"]:
                item = normalize_element(element, area_code)
                if not item or not geometry_contains(boundary, float(item["lng"]), float(item["lat"])):
                    continue
                if str(item["id"]) not in toilets_by_id:
                    accepted += 1
                toilets_by_id.setdefault(str(item["id"]), item)
        if timestamps:
            source_timestamps[area_code] = max(timestamps)
        print(f"{area_code}: {accepted} public toilets")

    toilets = sorted(
        toilets_by_id.values(),
        key=lambda item: (str(item["area"]), float(item["lat"]), float(item["lng"]), str(item["id"])),
    )
    by_area = Counter(str(item["area"]) for item in toilets)
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "gridCellDegrees": cell_size,
        "areas": [AREA_NAMES[code] for code in area_codes],
        "source": {
            "name": "OpenStreetMap via Overpass API",
            "endpoint": endpoint,
            "boundaryEndpoint": boundary_endpoint,
            "copyright": "OpenStreetMap contributors",
            "license": "https://www.openstreetmap.org/copyright",
            "timestamps": source_timestamps,
        },
        "counts": {
            "total": len(toilets),
            "byArea": {AREA_NAMES[code]: by_area.get(AREA_NAMES[code], 0) for code in area_codes},
        },
        "toilets": toilets,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="normalized JSON output path")
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR, help="raw response checkpoint directory")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Overpass interpreter endpoint")
    parser.add_argument(
        "--boundary-endpoint",
        default=DEFAULT_BOUNDARY_ENDPOINT,
        help="Nominatim endpoint used once per cached prefecture boundary",
    )
    parser.add_argument(
        "--area",
        action="append",
        choices=AREA_NAMES,
        dest="areas",
        help="prefecture code to download; repeat as needed (default: all supported areas)",
    )
    parser.add_argument("--offline", action="store_true", help="build only from cached raw responses")
    parser.add_argument("--refresh", action="store_true", help="replace existing raw response checkpoints")
    parser.add_argument(
        "--refresh-boundaries",
        action="store_true",
        help="replace cached prefecture boundary GeoJSON",
    )
    parser.add_argument("--cell-size", type=float, default=0.25, help="grid cell size in degrees")
    parser.add_argument("--delay", type=float, default=5.0, help="seconds between new cell requests")
    parser.add_argument("--query-timeout", type=int, default=60, help="Overpass query timeout declaration")
    parser.add_argument("--request-timeout", type=int, default=90, help="HTTP request timeout")
    parser.add_argument("--retries", type=int, default=8, help="retries for rate limits and transient failures")
    parser.add_argument("--backoff", type=float, default=30.0, help="initial retry delay in seconds")
    parser.add_argument(
        "--cache-max-age-days",
        type=float,
        default=10.0,
        help="reuse successful grid checkpoints newer than this many days",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.offline and args.refresh:
        print("--offline and --refresh cannot be used together", file=sys.stderr)
        return 2
    if not 0.05 <= args.cell_size <= 1.0:
        print("--cell-size must be between 0.05 and 1.0 degrees", file=sys.stderr)
        return 2
    if args.cache_max_age_days <= 0:
        print("--cache-max-age-days must be greater than zero", file=sys.stderr)
        return 2
    area_codes = list(dict.fromkeys(args.areas or AREA_NAMES))
    cache_dir = Path(args.cache_dir) / f"grid-{args.cell_size:.3f}"
    try:
        dataset = build_dataset(
            area_codes,
            cache_dir,
            offline=args.offline,
            refresh=args.refresh,
            endpoint=args.endpoint,
            query_timeout=max(1, args.query_timeout),
            request_timeout=max(1, args.request_timeout),
            retries=max(0, args.retries),
            backoff_seconds=max(1.0, args.backoff),
            delay_seconds=max(0.0, args.delay),
            cell_size=args.cell_size,
            boundary_endpoint=args.boundary_endpoint,
            refresh_boundaries=args.refresh_boundaries,
            cache_max_age_days=args.cache_max_age_days,
        )
    except FileNotFoundError as error:
        print(f"missing cached response: {error.filename}", file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError, urllib.error.URLError) as error:
        print(f"public toilet build failed: {error}", file=sys.stderr)
        return 1
    output = Path(args.output)
    if output.exists():
        try:
            existing = read_json(output)
        except (OSError, json.JSONDecodeError):
            existing = None
        if semantic_dataset(existing) == semantic_dataset(dataset):
            print(f"unchanged {output} ({dataset['counts']['total']} public toilets)")
            return 0
    write_json(output, dataset)
    counts = dataset["counts"]
    print(f"wrote {output} with {counts['total']} public toilets")
    for area, count in counts["byArea"].items():
        print(f"  {area}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
