#!/usr/bin/env python3
"""Run independent location generators locally and optionally publish changed JSON."""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Source:
    name: str
    script: str
    output: str
    collection: str
    minimum_count: int


SOURCES = (
    Source("anytime-fitness", "generate_anytime_fitness.py", "data/anytime-fitness.json", "locations", 500),
    Source("withgreen", "generate_withgreen.py", "data/withgreen.json", "locations", 25),
    Source("crisp", "generate_crisp.py", "data/crisp.json", "locations", 40),
    Source("starbucks", "generate_starbucks.py", "data/starbucks.json", "locations", 650),
    Source("familymart", "generate_familymart.py", "data/familymart.json", "locations", 4000),
    Source("seven-eleven", "generate_seven_eleven.py", "data/seven-eleven.json", "locations", 6000),
    Source("major-stations", "generate_major_stations.py", "data/major-stations.json", "stations", 160),
    Source(
        "kanagawa-stations",
        "generate_kanagawa_stations.py",
        "data/kanagawa-stations.json",
        "stations",
        330,
    ),
    Source("mountain-peaks", "generate_mountain_peaks.py", "data/mountain-peaks.json", "peaks", 100),
    Source("public-toilets", "generate_public_toilets.py", "data/public-toilets.json", "toilets", 1),
    Source(
        "docomo-cycle-ports",
        "download_docomo_cycle_ports.py",
        "data/docomo-cycle-ports.json",
        "ports",
        1500,
    ),
    Source("runner-shops", "generate_runner_shops.py", "data/runner-shops.json", "locations", 1),
)
SOURCE_BY_NAME = {source.name: source for source in SOURCES}


def read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def semantic_payload(payload: object) -> object:
    if not isinstance(payload, dict):
        return payload
    normalized = copy.deepcopy(payload)
    normalized.pop("generatedAt", None)
    source = normalized.get("source")
    if isinstance(source, dict):
        source.pop("timestamps", None)
    return normalized


def validate_snapshot(source: Source, path: Path) -> dict[str, object]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{source.name}: root must be a JSON object")
    items = payload.get(source.collection)
    if not isinstance(items, list) or len(items) < source.minimum_count:
        count = len(items) if isinstance(items, list) else 0
        raise ValueError(
            f"{source.name}: expected at least {source.minimum_count} {source.collection}, received {count}"
        )
    ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{source.name}: item {index} is not an object")
        item_id = str(item.get("id") or "")
        if not item_id or item_id in ids:
            raise ValueError(f"{source.name}: item {index} has a missing or duplicate id")
        ids.add(item_id)
        try:
            lat = float(item["lat"])
            lng = float(item["lng"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"{source.name}: item {item_id} has invalid coordinates") from error
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError(f"{source.name}: item {item_id} has invalid coordinates")
    counts = payload.get("counts")
    if isinstance(counts, dict) and counts.get("total") != len(items):
        raise ValueError(f"{source.name}: counts.total does not match {source.collection}")
    return payload


def generator_command(source: Source, output: Path, args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / source.script),
        "--output",
        str(output),
    ]
    if source.name == "public-toilets":
        command.extend(
            [
                "--cache-dir",
                str(REPO_ROOT / ".cache" / "public-toilets"),
                "--endpoint",
                args.public_toilet_endpoint,
                "--delay",
                str(args.public_toilet_delay),
                "--cache-max-age-days",
                str(args.max_age_days),
            ]
        )
    return command


def promote_snapshot(staged_path: Path, output_path: Path, payload: dict[str, object]) -> bool:
    if output_path.exists() and semantic_payload(read_json(output_path)) == semantic_payload(payload):
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(dir=output_path.parent, suffix=".tmp")
    os.close(file_descriptor)
    try:
        shutil.copyfile(staged_path, temporary_name)
        os.replace(temporary_name, output_path)
        os.chmod(output_path, 0o644)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return True


def git_output(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def publish(outputs: list[str], message: str) -> None:
    staged_before = git_output("diff", "--cached", "--name-only")
    if staged_before:
        raise RuntimeError("refusing to publish while other changes are already staged")
    subprocess.run(["git", "add", "--", *outputs], cwd=REPO_ROOT, check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet", "--", *outputs], cwd=REPO_ROOT).returncode == 0:
        print("No location-data changes to publish")
        return
    subprocess.run(["git", "commit", "-m", message, "--", *outputs], cwd=REPO_ROOT, check=True)
    subprocess.run(["git", "push"], cwd=REPO_ROOT, check=True)


def selected_sources(names: list[str] | None, skip_public_toilets: bool) -> list[Source]:
    selected_names = names or ["all"]
    if "all" in selected_names:
        selected = list(SOURCES)
    else:
        selected = [SOURCE_BY_NAME[name] for name in dict.fromkeys(selected_names)]
    if skip_public_toilets:
        selected = [source for source in selected if source.name != "public-toilets"]
    return selected


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        action="append",
        choices=("all", *SOURCE_BY_NAME),
        help="source to refresh; repeat as needed (default: all)",
    )
    parser.add_argument(
        "--skip-public-toilets",
        action="store_true",
        help="refresh all requested sources except the long-running public-toilet snapshot",
    )
    parser.add_argument("--max-age-days", type=float, default=10.0, help="public-toilet checkpoint TTL")
    parser.add_argument("--public-toilet-delay", type=float, default=5.0, help="seconds between Overpass calls")
    parser.add_argument(
        "--public-toilet-endpoint",
        default="https://overpass.private.coffee/api/interpreter",
        help="Overpass endpoint for the public-toilet generator",
    )
    parser.add_argument("--publish", action="store_true", help="commit and push changed JSON files")
    parser.add_argument("--watch", action="store_true", help="repeat the refresh in this process")
    parser.add_argument("--interval-days", type=float, default=10.0, help="days between --watch runs")
    parser.add_argument(
        "--commit-message",
        default="Update static location data",
        help="commit message used with --publish",
    )
    return parser.parse_args(argv)


def refresh_once(args: argparse.Namespace, sources: list[Source]) -> int:
    staging_parent = REPO_ROOT / ".cache" / "location-refresh"
    staging_parent.mkdir(parents=True, exist_ok=True)
    failures: list[tuple[str, str]] = []
    changed_outputs: list[str] = []
    with tempfile.TemporaryDirectory(dir=staging_parent) as temporary_directory:
        temporary_root = Path(temporary_directory)
        staged: list[tuple[Source, Path, dict[str, object]]] = []
        for source in sources:
            try:
                output = temporary_root / Path(source.output).name
                print(f"\n== {source.name} ==")
                subprocess.run(generator_command(source, output, args), cwd=REPO_ROOT, check=True)
                staged.append((source, output, validate_snapshot(source, output)))
            except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
                failures.append((source.name, str(error)))
                print(
                    f"{source.name} failed; keeping the existing {source.output}: {error}",
                    file=sys.stderr,
                )

        for source, staged_path, payload in staged:
            try:
                destination = REPO_ROOT / source.output
                if promote_snapshot(staged_path, destination, payload):
                    changed_outputs.append(source.output)
                    print(f"promoted {source.output}")
                else:
                    print(f"unchanged {source.output}")
            except (OSError, ValueError, json.JSONDecodeError) as error:
                failures.append((source.name, str(error)))
                print(
                    f"{source.name} could not be promoted; keeping the existing {source.output}: {error}",
                    file=sys.stderr,
                )

    if changed_outputs:
        print(f"\nUpdated {len(changed_outputs)} snapshot(s)")
    else:
        print("\nAll successful snapshots are already current")
    if args.publish and changed_outputs:
        try:
            publish(changed_outputs, args.commit_message)
        except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
            print(f"JSON files were updated locally, but publishing failed: {error}", file=sys.stderr)
            return 1
    elif changed_outputs:
        print("Changes are local only; rerun with --publish to commit and push them")
    if failures:
        print(f"\n{len(failures)} source(s) failed:", file=sys.stderr)
        for name, error in failures:
            print(f"  {name}: {error}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.max_age_days <= 0:
        print("--max-age-days must be greater than zero", file=sys.stderr)
        return 2
    if args.interval_days <= 0:
        print("--interval-days must be greater than zero", file=sys.stderr)
        return 2
    sources = selected_sources(args.source, args.skip_public_toilets)
    if not sources:
        print("No sources selected", file=sys.stderr)
        return 2
    if not args.watch:
        return refresh_once(args, sources)

    interval_seconds = args.interval_days * 24 * 60 * 60
    try:
        while True:
            refresh_once(args, sources)
            next_run = datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
            print(f"\nNext refresh: {next_run.isoformat()}")
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nLocation refresh watch stopped")
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
