# Static Run Planner

This folder is a backend-free run planner that can be hosted as static files.

Files:

- `index.html` - the standalone map UI
- `locations.js` - generated store overlay data

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
- Change `Radius km` to redraw the distance radius.
- Drag the center marker for finer placement.
- Use brand and area filters to reduce visible store markers.
- Use the brand key to read marker abbreviations: `AF`, `WG`, and `CR` for CRISP SALAD WORKS.
- Use the `EN` / `日本語` switch to change the UI language.
