# Static Run Planner

This folder is a backend-free run planner that can be hosted as static files.

Files:

- `index.html` - the standalone map UI
- `data/*.json` - one independently loaded static snapshot per location type
- `scripts/generate_*.py` - one local generator per source
- `scripts/refresh_location_data.py` - validated local refresh and optional Git publisher

The live page does not query location providers. Each map layer reads its own
JSON file with `cache: no-store`; a missing or invalid source disables only that
source's row. Every JSON request also carries the visible `APP_VERSION` as a
cache-busting query parameter. Each snapshot records its own `schemaVersion`
and `generatedAt`, while Git history records the actual content changes.

## Local location refresh

Refresh every source locally:

```bash
python3 scripts/refresh_location_data.py
```

The public-toilet generator uses a rate-limited grid and persistent checkpoints
under `.cache/public-toilets/`. A complete first run can take hours. Run it in a
screen session:

```bash
screen -S run-planner-locations
python3 scripts/refresh_location_data.py --watch --publish
```

Detach with `Ctrl-A`, then `D`. Reattach with:

```bash
screen -r run-planner-locations
```

`--watch` starts immediately, then runs again every 10 days. Stop it with
`Ctrl-C`.

Successful toilet grid cells are reused for 10 days. An interrupted run resumes
from the remaining stale or missing cells. If one source fails, its existing
JSON remains untouched while other valid sources can still update and publish.
The command returns a nonzero status so the failed source is visible to
monitoring.

For a fast refresh that excludes the long-running toilet source:

```bash
python3 scripts/refresh_location_data.py --skip-public-toilets
```

Refresh one or more sources:

```bash
python3 scripts/refresh_location_data.py --source starbucks
python3 scripts/refresh_location_data.py --source familymart --source seven-eleven
```

After reviewing local changes, generate, commit, and push only changed JSON:

```bash
python3 scripts/refresh_location_data.py --publish
```

This is intentionally a local operation. There is no GitHub Actions updater.
The publisher refuses to run when unrelated changes are already staged.

Independent snapshots and generators:

| Snapshot | Generator |
| --- | --- |
| `data/anytime-fitness.json` | `scripts/generate_anytime_fitness.py` |
| `data/withgreen.json` | `scripts/generate_withgreen.py` |
| `data/crisp.json` | `scripts/generate_crisp.py` |
| `data/starbucks.json` | `scripts/generate_starbucks.py` |
| `data/familymart.json` | `scripts/generate_familymart.py` |
| `data/seven-eleven.json` | `scripts/generate_seven_eleven.py` |
| `data/major-stations.json` | `scripts/generate_major_stations.py` |
| `data/public-toilets.json` | `scripts/generate_public_toilets.py` |
| `data/docomo-cycle-ports.json` | `scripts/download_docomo_cycle_ports.py` |
| `data/runner-shops.json` | `scripts/generate_runner_shops.py` |

The page still uses public GSI raster tiles and the Leaflet CDN, but it does not
call live location APIs, the CardioTrack Flask app, or local MBTiles.

GitHub Pages:

```bash
git remote add origin git@github.com:YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

Then set GitHub Pages to deploy from the `main` branch and `/` root. The site is
ready for Pages because `index.html` is at the repository root.

Use:

- Use the `<` / `>` side tab to open or close the planner panel.
- Rotate with two fingers on touch devices or hold Shift while dragging on
  desktop. Use the `N` control to return the map to north-up.
- Click the map to place the route center.
- Use the `Radius km` dropdown to choose a whole-kilometer radius from 1 to 43.
- Drag the center marker for finer placement.
- Use the pencil button to draw a direct-line route. The starting point defaults
  to the current circle center, which is also the last map-click center.
- The route draw row shows total drawn distance, starting at `0.00 km`.
- Once the start is set, draw mode zooms to level 16 and locks zoom while
  editing the route. Each map click adds the next waypoint directly.
- Click a visible `AF`, `WG`, `CR`, or `SB` marker while drawing to add that
  location as the next waypoint, with an option to set it as the route goal.
- Click an existing route segment to add a draggable control point between the
  surrounding waypoints. This reopens edit mode if the route was locked.
- Normal endpoint clicks show a compact distance popup. Right-click the route or
  map while drawing to open the full route action menu.
- Drawn routes replace the radius estimate with total route distance plus
  pace-based estimated time beside the radius and pace controls.
- Use `Undo` to remove waypoints back to the starting point, `Done` to lock and
  save the route, and `Start over` to clear it and begin again.
- Use `Export GPX` after selecting `Done` to download the locked route as a GPX
  file. Exported geometry uses the same direct-line points shown on the map and
  includes GPX 1.1 route and track data for broader app compatibility.
- Use `Map elements` / `地図要素` to toggle curated locations, convenience
  stores, major stations, public bathrooms, Docomo cycle ports, and live rain
  radar from one list.
- Area filters sit below map elements and reduce visible store markers.
- Convenience-store markers are off by default. Turn on `Family Mart` or `7/11` at zoom level 14 or closer.
- Toggle `Major stations` to show or hide small black landmark labels for roughly 100 high-traffic stations in the supported areas.
- Toggle `🚾 Public bathrooms` to show public-toilet markers from OpenStreetMap.
  They appear at zoom level 15 or closer, and can be clicked while drawing a
  route to add the bathroom as a waypoint or goal.
- Toggle `🚲 Docomo cycle ports` to show the static Tokyo Bike Share port
  snapshot at zoom level 15 or closer. The layer is off by default, and its
  markers can be added to a drawn route as waypoints or goals.
- Toggle `☔ Rain radar` / `雨雲レーダー` at the bottom of Map elements to
  show the latest RainViewer precipitation frame. The layer is off by default,
  uses RainViewer's original 512-pixel tiles and palette, and refreshes its
  metadata every five minutes.
- The runner emoji marker is a standalone running shop marker and is not part of the brand key.
- Use the `EN` / `日本語` switch to change the UI language.
