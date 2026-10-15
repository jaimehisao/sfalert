#!/usr/bin/env python3
"""Screenshot the SFALERT map UI with a headless browser.

Starts the server on a scratch port, loads the UI with a deterministic
state (the app syncs its filters into the URL), and writes a PNG. Basemap
tiles are rewritten to OpenStreetMap by default: CARTO rate-limits
anonymous tile bursts and answers with an "API KEY REQUIRED" watermark
tile, which would make screenshots nondeterministic. Pass --keep-tiles
to capture the real thing.

Requires no install - uv fetches playwright on demand:

    uv run --with playwright -- python tools/screenshot.py --out /tmp/ui.png
    uv run --with playwright -- python tools/screenshot.py --tiles esri --out /tmp/ui.png

    # a specific state and viewport
    uv run --with playwright -- python tools/screenshot.py \
        --window 90d --search market --view mobile --out /tmp/mobile.png

    # the empty state (no matching calls)
    uv run --with playwright -- python tools/screenshot.py --window 3h --out /tmp/empty.png

Flags map onto the UI's own URL state, so a screenshot is always a state
you can also hand to a reviewer to reproduce.
"""

from __future__ import annotations

import argparse
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARTO_HOST = "basemaps.cartocdn.com"
OSM_HOST = "tile.openstreetmap.org"
ESRI = "esri"
ESRI_SERVICE = (
    "https://server.arcgisonline.com/ArcGIS/rest/services"
    "/Canvas/World_Dark_Gray_Base/MapServer/tile"
)

# CARTO tile paths are /{style}/{z}/{x}/{y}{@2x}.png; Esri wants /{z}/{y}/{x}.
_CARTO_HOST_RE = re.compile(r"//[a-d]\.basemaps\.cartocdn\.com/")
_CARTO_PATH_RE = re.compile(r"/[^/]+/(\d+)/(\d+)/(\d+)(?:@2x)?\.png")


def _swap_tiles(host: str, url: str) -> str:
    if host == ESRI:
        match = _CARTO_PATH_RE.search(url)
        if not match:
            return url
        z, x, y = match.groups()
        return f"{ESRI_SERVICE}/{z}/{y}/{x}"
    return _CARTO_HOST_RE.sub(f"//{host}/", url)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _start_server(port: int) -> subprocess.Popen:
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "sfalert",
            "serve",
            "--no-poll",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            import urllib.request

            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/meta", timeout=2
            ):
                return proc
        except Exception:
            if proc.poll() is not None:
                raise SystemExit("server exited during startup")
            time.sleep(0.25)
    proc.terminate()
    raise SystemExit("server did not become ready in time")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", default="90d")
    parser.add_argument("--category", default=None)
    parser.add_argument("--district", default=None)
    parser.add_argument("--search", default=None, help="q parameter")
    parser.add_argument("--open-only", action="store_true")
    parser.add_argument("--noise", action="store_true", help="show routine calls")
    parser.add_argument("--view", choices=("desktop", "mobile"), default="desktop")
    parser.add_argument(
        "--tiles",
        choices=("osm", "esri"),
        default="osm",
        help="keyless basemap to render with; pass an empty value for the app default",
    )
    parser.add_argument("--keep-tiles", action="store_true", help="do not swap CARTO")
    parser.add_argument("--wait", type=int, default=1200, help="settle time after load (ms)")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    from urllib.parse import urlencode

    from playwright.sync_api import sync_playwright

    port = _free_port()
    server = _start_server(port)
    try:
        params: dict[str, str] = {"window": args.window}
        if args.category:
            params["category"] = args.category
        if args.district:
            params["district"] = args.district
        if args.search:
            params["q"] = args.search
        if args.open_only:
            params["open"] = "1"
        if args.noise:
            params["noise"] = "1"
        url = f"http://127.0.0.1:{port}/?{urlencode(params)}"

        size = (
            {"width": 1440, "height": 900}
            if args.view == "desktop"
            else {"width": 390, "height": 844}
        )
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport=size)
            if not args.keep_tiles:
                host = OSM_HOST if args.tiles == "osm" else ESRI
                page.route(
                    _CARTO_HOST_RE,
                    lambda route, request: route.continue_(
                        url=_swap_tiles(host, request.url)
                    ),
                )
            errors: list[str] = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(args.wait)
            page.screenshot(path=str(out_path))
            browser.close()

        if errors:
            print(f"warning: page errors during load: {errors[:3]}", file=sys.stderr)
        print(f"{out_path}  ({out_path.stat().st_size / 1024:.0f} KB)")
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    main()
