# SFALERT

Local store + live map for San Francisco **CAD** (Computer Aided Dispatch) calls.

The city publishes 911 / law-enforcement dispatches on [DataSF](https://data.sfgov.org/Public-Safety/Law-Enforcement-Dispatched-Calls-for-Service-Real-/gnap-fj3t). This app pulls that feed into SQLite on your machine, then draws a live map: incident cards, pins, and a heatmap.

Traffic stops and cites are **kept** in the heatmap. They cluster by intersection and are one of the stronger CAD hotspot signals. Passing calls and other radio noise are hidden by default.

## Run

Python 3.11+ , stdlib only.

```bash
python -m sfalert
```

That backfills ~30 days of closed calls, snapshots the real-time 48h window, then serves:

[http://127.0.0.1:8765](http://127.0.0.1:8765)

Useful splits:

```bash
python -m sfalert ingest --days 30    # fill SQLite
python -m sfalert serve               # map UI + poll every 2 min
```

Data lives in `data/sfalert.db`. Optional Socrata token: `SFALERT_APP_TOKEN`.

## What you are looking at

| Source | Dataset | Cadence |
|---|---|---|
| Live CAD | `gnap-fj3t` | ~10 min delay, last 48 hours |
| History | `2zdj-bwza` | daily, closed calls |

Locations are snapped to intersections by the city. Sensitive calls often have no coordinates. This is not 911 and not AlertSF.

## Filters

- **Hide routine** — drops passing calls, prisoner transport, etc. Does **not** drop traffic stops.
- Category chips — violence, theft, traffic, welfare, …
- Time window — 3h through 30d
- District — SFPD districts

## Tests

Stdlib `unittest`, no extra deps. From the repo root:

```bash
make test
```

GitHub Actions runs the same target on `ubuntu-latest` (`push` to `main` and pull requests). Pushes to `main` and `v*` tags also publish a container image to GHCR:

```bash
docker pull ghcr.io/jaimehisao/sfalert:latest
docker run --rm -p 8765:8765 -v sfalert-data:/app/data ghcr.io/jaimehisao/sfalert:latest
```

Build locally with `make docker`. The image listens on `0.0.0.0:8765` and stores SQLite under `/app/data`.
