from __future__ import annotations

import json
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import ingest as ingest_mod
from .categories import category_meta
from .db import ROOT, connect
from .query import heatmap_points, list_incidents, stats

WEB_DIR = ROOT / "web"
POLL_SECONDS = 120


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        if self.path.startswith("/api/"):
            print(f"{self.address_string()} {fmt % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/api/"):
            self._api(parsed.path, parse_qs(parsed.query))
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/refresh":
            try:
                result = ingest_mod.ingest(days=30, realtime=True, backfill=False)
                self._json(result)
            except Exception as exc:
                self._json({"error": str(exc)}, 500)
            return
        self._json({"error": "not found"}, 404)

    def _api(self, path: str, query: dict[str, list[str]]) -> None:
        def one(name: str, default: str | None = None) -> str | None:
            values = query.get(name)
            if not values:
                return default
            value = values[0].strip()
            return value or default

        window = one("window", "24h") or "24h"
        category = one("category")
        district = one("district")
        status = one("status")
        hide_routine = one("hide_routine", "1") != "0"
        limit = int(one("limit", "200") or "200")
        limit = max(1, min(limit, 500))

        conn = connect()
        try:
            if path == "/api/incidents":
                self._json(
                    list_incidents(
                        conn,
                        window=window,
                        category=category,
                        district=district,
                        hide_routine=hide_routine,
                        status=status,
                        limit=limit,
                    )
                )
                return
            if path == "/api/heatmap":
                self._json(
                    {
                        "points": heatmap_points(
                            conn,
                            window=window,
                            category=category,
                            district=district,
                            hide_routine=hide_routine,
                        )
                    }
                )
                return
            if path == "/api/stats":
                self._json(
                    stats(
                        conn,
                        window=window,
                        category=category,
                        district=district,
                        hide_routine=hide_routine,
                    )
                )
                return
            if path == "/api/meta":
                self._json({"categories": category_meta(), "windows": list(_WINDOWS)})
                return
            self._json({"error": "not found"}, 404)
        except Exception as exc:
            self._json({"error": str(exc)}, 500)
        finally:
            conn.close()

    def _json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


_WINDOWS = ["3h", "6h", "12h", "24h", "7d", "30d"]


def _poll_forever(stop: threading.Event) -> None:
    while not stop.wait(POLL_SECONDS):
        try:
            ingest_mod.ingest(days=30, realtime=True, backfill=False)
        except Exception as exc:
            print(f"poll failed: {exc}")


def serve(host: str = "127.0.0.1", port: int = 8765, poll: bool = True) -> None:
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    if poll:
        threading.Thread(target=_poll_forever, args=(stop,), daemon=True).start()
        print(f"Polling CAD every {POLL_SECONDS}s")
    httpd = ThreadingHTTPServer((host, port), partial(Handler))
    print(f"SFALERT  http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        stop.set()
        httpd.server_close()
