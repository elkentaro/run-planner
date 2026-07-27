# Static Run Planner

This folder is a backend-free run planner that can be hosted as static files.

Files:

- `index.html` - the standalone map UI
- `locations.js` - generated store overlay data
- `major-stations.js` - generated major-station visual cue data
- `convenience-stores.json` - generated convenience-store overlay data, loaded only when enabled
- `docomo-cycle-ports.json` - generated Docomo cycle-port overlay data, loaded only when enabled

Rebuild the store data:

```bash
python3 scripts/build_static_run_planner_data.py
```

Rebuild the convenience-store data:

```bash
python3 scripts/download_convenience_stores.py
```

Refresh the Docomo cycle-port snapshot from the public Tokyo Bike Share My Map:

```bash
python3 scripts/download_docomo_cycle_ports.py
```

This currently downloads FamilyMart and 7-Eleven for Tokyo, Kanagawa, Saitama,
Chiba, and Tochigi. Lawson is intentionally not included yet because a reliable
source is not wired into the downloader.

The page uses public GSI raster tiles, the Leaflet CDN, and the OpenStreetMap
Overpass API when public bathrooms are enabled. It does not call the CardioTrack
Flask app or use local MBTiles.

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
- Use `Map elements` / `地図要素` to toggle curated locations, convenience stores, major stations, public bathrooms, and Docomo cycle ports from one list.
- Area filters sit below map elements and reduce visible store markers.
- Convenience-store markers are off by default. Turn on `Family Mart` or `7/11` at zoom level 14 or closer.
- Toggle `Major stations` to show or hide small black landmark labels for roughly 100 high-traffic stations in the supported areas.
- Toggle `🚾 Public bathrooms` to show public-toilet markers from OpenStreetMap.
  They appear at zoom level 15 or closer, and can be clicked while drawing a
  route to add the bathroom as a waypoint or goal.
- Toggle `🚲 Docomo cycle ports` to show the static Tokyo Bike Share port
  snapshot at zoom level 15 or closer. The layer is off by default, and its
  markers can be added to a drawn route as waypoints or goals.
- The runner emoji marker is a standalone running shop marker and is not part of the brand key.
- Use the `EN` / `日本語` switch to change the UI language.
