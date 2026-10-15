# SFALERT

Local store + live map for San Francisco **CAD** (Computer Aided Dispatch) calls.

The city publishes 911 / law-enforcement dispatches on [DataSF](https://data.sfgov.org/Public-Safety/Law-Enforcement-Dispatched-Calls-for-Service-Real-/gnap-fj3t). This app pulls that feed into SQLite on your machine, then draws a live map: incident cards, pins, and a heatmap.

Traffic stops and cites are **kept** in the heatmap. They cluster by intersection and are one of the stronger CAD hotspot signals. Passing calls and other radio noise are hidden by default.

## Run

Python 3.11+ , stdlib only.

```bash
python -m sfalert
```

Or install it (`pip install .`) and run the `sfalert` command from
anywhere - `python -m sfalert` still works from a checkout.

That backfills ~30 days of closed calls, snapshots the real-time 48h window, then serves:

[http://127.0.0.1:8765](http://127.0.0.1:8765)

Useful splits:

```bash
python -m sfalert ingest --days 30    # fill SQLite
python -m sfalert serve               # map UI + poll every 2 min
```

Data lives in `data/sfalert.db`. Optional Socrata token: `SFALERT_APP_TOKEN`.

## Basemap tiles

The map draws incident data locally; only basemap tiles come from the
internet. The provider is configurable, trading looks against privacy and
availability:

| `SFALERT_BASEMAP` | Provider | Notes |
|---|---|---|
| `carto-dark` *(default)* | CARTO dark | long-standing look; anonymous tile bursts can get rate-limited (the map shows "API KEY REQUIRED" watermarks) |
| `esri-dark` | Esri Dark Gray Canvas | keyless, dark, street labels; closest look to the default |
| `osm` | OpenStreetMap standard | keyless; light themed |
| `none` | no basemap | **zero external requests** — pins and heatmap still work |

The env var sets the default; `?basemap=osm` in the URL (or the **Map**
selector in the top bar) overrides it per session. Every tile request
reveals your IP and pan/zoom pattern to the provider, which is what
`none` exists for. All four are HTTPS static raster tiles — none can
execute script in the page. Docker:

```bash
docker run --rm -p 8765:8765 -e SFALERT_BASEMAP=esri-dark \
  -v sfalert-data:/app/data ghcr.io/jaimehisao/sfalert:latest
```

## What you are looking at

| Source | Dataset | Cadence |
|---|---|---|
| Live CAD | `gnap-fj3t` | ~10 min delay, last 48 hours |
| History | `2zdj-bwza` | daily, closed calls |

Locations are snapped to intersections by the city. Sensitive calls often have no coordinates. This is not 911 and not AlertSF.

## Filters

- **Hide routine** — drops passing calls, prisoner transport, etc. Does **not** drop traffic stops.
- Category chips — violence, theft, traffic, welfare, …
- Time window — 3h through 90d
- District — SFPD districts
- Search — call type, street, neighborhood, district, CAD number, or agency; scopes the feed, the pins, and the stats panels

## Tests

Stdlib `unittest`, no extra deps. From the repo root:

```bash
make test
```

`make coverage` runs the same suite under coverage and fails below 85%
(branch coverage, scoped to the `sfalert/` package). It needs the dev extra:
`pip install -e ".[dev]"`. GitHub Actions runs the coverage gate on every
`push` to `main` and pull request.

### UI screenshots

`tools/screenshot.py` renders the map UI headlessly for visual checks —
useful before/after a UI change, since a state in the UI is also a URL:

```bash
uv run --with playwright -- python tools/screenshot.py --window 90d --out /tmp/ui.png

# a filtered state, in a phone viewport
uv run --with playwright -- python tools/screenshot.py \
    --district MISSION --search stabbing --view mobile --out /tmp/mobile.png
```

Flags mirror the app's own URL state (`--window`, `--category`,
`--district`, `--search`, `--open-only`, `--noise`, `--view`). Basemap tiles are
rewritten to a keyless provider so output is deterministic — CARTO answers
anonymous tile bursts with an “API KEY REQUIRED” watermark. Use `--tiles osm`
(OpenStreetMap, light) or `--tiles esri` (Esri Dark Gray Canvas, dark) to
compare looks, and `--keep-tiles` to render the app's default unchanged.

GitHub Actions runs the same target on `ubuntu-latest` (`push` to `main` and pull requests). Pushes to `main` and `v*` tags also publish a container image to GHCR:

```bash
docker pull ghcr.io/jaimehisao/sfalert:latest
docker run --rm -p 8765:8765 -v sfalert-data:/app/data ghcr.io/jaimehisao/sfalert:latest
```

Build locally with `make docker`. The image listens on `0.0.0.0:8765` and stores SQLite under `/app/data`.
