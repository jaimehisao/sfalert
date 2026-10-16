"""Basemap tile providers for the map UI.

Tile endpoints are third-party services: every tile request reveals the
viewer's IP address and pan/zoom behavior to the provider's operator, and
each provider has its own rate limits and terms of service. All URLs here
are HTTPS and serve static raster tiles (Leaflet loads them through <img>,
so no provider can execute script in the page), but the choice of provider
is the operator's - hence this registry plus the "none" option, which
removes the external request entirely.
"""

from __future__ import annotations

import os

ENV_VAR = "SFALERT_BASEMAP"
DEFAULT_BASEMAP = "carto-dark"

BASEMAPS: dict[str, dict[str, object]] = {
    "carto-dark": {
        "label": "Dark · CARTO",
        "url": "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        "subdomains": "abcd",
        # Nominal ceiling per CARTO's docs; unverified here because CARTO
        # answers this environment with its "API KEY REQUIRED" watermark tile
        # at every zoom level.
        "max_native_zoom": 20,
        "attribution": (
            '&copy; <a href="https://www.openstreetmap.org/copyright">'
            "OpenStreetMap</a> &copy; "
            '<a href="https://carto.com/attributions">CARTO</a>'
        ),
    },
    "esri-dark": {
        "label": "Dark gray · Esri",
        "url": (
            "https://server.arcgisonline.com/ArcGIS/rest/services"
            "/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        ),
        "subdomains": "",
        # Verified against live tiles: SF has real coverage to z16 and
        # "Map data not yet available" placeholders beyond it, so the UI
        # upscales from z16 instead of drawing those placeholder tiles.
        "max_native_zoom": 16,
        "attribution": 'Tiles &copy; <a href="https://www.esri.com/">Esri</a>',
    },
    "osm": {
        "label": "Standard · OpenStreetMap",
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "subdomains": "",
        # Verified: real rasters to z19, nothing at z20.
        "max_native_zoom": 19,
        "attribution": (
            '&copy; <a href="https://www.openstreetmap.org/copyright">'
            "OpenStreetMap</a> contributors"
        ),
    },
    "none": {
        "label": "No basemap · offline",
        "url": None,
        "subdomains": "",
        "max_native_zoom": None,
        "attribution": "",
    },
}


def basemap_meta() -> list[dict[str, object]]:
    """Provider list for /api/meta, including everything the UI needs to draw a layer."""
    return [{"id": key, **meta} for key, meta in BASEMAPS.items()]


def resolve(user_choice: str | None = None, env: str | None = None) -> str:
    """Pick the active provider: an explicit choice, then env, then default.

    Unknown values fall back to the default rather than raising - this runs
    on every request hot path from a query param.
    """
    env_value = env if env is not None else os.environ.get(ENV_VAR)
    for candidate in (user_choice, env_value):
        if candidate and candidate in BASEMAPS:
            return candidate
    return DEFAULT_BASEMAP


def provider(active: str | None = None) -> dict[str, object]:
    """The full config (id, url, attribution, subdomains) for the active provider."""
    key = resolve(active)
    return {"id": key, **BASEMAPS[key]}
