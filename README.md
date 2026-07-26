# Static Run Planner

This folder is a backend-free run planner that can be hosted as static files.

Files:

- `index.html` - the standalone map UI
- `locations.js` - generated store overlay data
- `major-stations.js` - generated major-station visual cue data

Rebuild the store data:

```bash
python3 scripts/build_static_run_planner_data.py
```

The page uses public GSI raster tiles and the Leaflet CDN. It does not call the
CardioTrack Flask app or use local MBTiles.

GitHub Pages:

```bash
git remote add origin git@github.com:YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

Then set GitHub Pages to deploy from the `main` branch and `/` root. The site is
ready for Pages because `index.html` is at the repository root.

Use:

- Use the `<` / `>` side tab to open or close the planner panel.
- Click the map to place the route center.
- Use the `Radius km` dropdown to choose a whole-kilometer radius from 1 to 43.
- Drag the center marker for finer placement.
- Use the pencil button to draw a direct-line route. The starting point defaults
  to the current circle center, which is also the last map-click center.
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
  track. Exported geometry uses the same direct-line points shown on the map.
- Use brand and area filters to reduce visible store markers.
- Use the brand key to read marker abbreviations: `AF`, `WG`, `CR` for CRISP SALAD WORKS, and `SB` for Starbucks.
- Toggle `Major stations` to show or hide small black landmark labels for roughly 100 high-traffic stations in the supported areas.
- The runner emoji marker is a standalone running shop marker and is not part of the brand key.
- Use the `EN` / `日本語` switch to change the UI language.
