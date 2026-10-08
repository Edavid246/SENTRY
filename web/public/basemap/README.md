# Offline basemap (demo)

Everything the `/map` street basemap needs is served by this app from this folder. The
browser never contacts a tile server, font CDN or other external host (AGENTS.md air-gap
rules). The pieces:

| File | What | Source |
|---|---|---|
| `demo-area.pmtiles` (~2 MB) | Vector tiles, zoom 0–15, bbox `5.25,9.15,5.70,9.55` (rural Niger State, Nigeria) | Protomaps daily planet build `20261008.pmtiles` (tiles schema v4), extracted with go-pmtiles 1.31.2 |
| `fonts/Noto Sans {Regular,Medium,Italic}/*.pbf` | Label glyphs, Latin ranges only (0–1023, 7680–7935, 8192–8447) | `protomaps/basemaps-assets` @ `028c18f` |
| `sprites/dark*` | POI and one-way arrow icons | `protomaps/basemaps-assets` @ `028c18f`, `sprites/v4` |

The style layers come from the `@protomaps/basemaps` npm package (dark flavor), built in
`web/src/lib/basemap.ts`.

## Licences

- Map data © OpenStreetMap contributors, available under the
  [Open Database Licence (ODbL)](https://opendatacommons.org/licenses/odbl/). The map shows
  the required attribution in its corner control.
- Noto Sans glyphs: SIL Open Font License, `fonts/OFL.txt`.
- Protomaps basemap styles and sprites: BSD-3-Clause / CC0 per the Protomaps repositories.

## Demo sites

The synthetic sensors, detections and UAS tracks (`backend/app/seed.py`, `_SITES` and the
`_ROUTE_*` tracks) were moved here from central Abuja so that fictitious military activity
is never drawn over a real city. The positions were checked against this extract: each
site is next to a road with **no buildings within about 1 km**, and the extract holds **no
military, airfield, barracks or prison features**. Nearest named localities are 7 km or
more away. Re-check if the sites or the extract change.

## Regenerate

```bash
# go-pmtiles release from github.com/protomaps/go-pmtiles (internet needed, build time only)
pmtiles extract https://build.protomaps.com/<YYYYMMDD>.pmtiles demo-area.pmtiles \
  --bbox=5.25,9.15,5.70,9.55 --maxzoom=15
```

Keep `BASEMAP_BOUNDS` in `web/src/lib/basemap.ts` equal to the bbox.
