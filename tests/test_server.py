import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sfalert.db import connect, upsert_incidents
from sfalert.server import Handler, _poll_forever, serve

from tests.helpers import incident_row


class ApiServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "sfalert.db"
        conn = connect(self.db_path)
        upsert_incidents(
            conn,
            [
                incident_row(cad_number="api-1"),
                incident_row(
                    cad_number="api-pass",
                    call_type_final_desc="PASSING CALL",
                    category="other",
                    routine=1,
                    severity=1,
                ),
            ],
        )
        conn.close()

        self._db_patch = patch("sfalert.db.DB_PATH", self.db_path)
        self._db_patch.start()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.httpd.server_address
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self._db_patch.stop()
        self.tmp.cleanup()

    def _get(self, path: str):
        with urlopen(self.base + path, timeout=5) as resp:
            body = resp.read()
            return resp.status, resp.headers.get("Content-Type"), body

    def test_serves_map_page_and_assets(self) -> None:
        status, ctype, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn(b"SFALERT", body)
        self.assertIn(b'id="map"', body)
        self.assertIn(b'id="q"', body)
        status, _, js = self._get("/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"heatmap", js)
        self.assertIn(b"escapeHtml", js)
        status, _, css = self._get("/styles.css")
        self.assertEqual(status, 200)
        self.assertIn(b"backdrop-filter", css)
        for asset in ("leaflet.js", "leaflet.css", "leaflet-heat.js"):
            status, _, body = self._get(f"/vendor/{asset}")
            self.assertEqual(status, 200, asset)
            self.assertGreater(len(body), 1000, asset)

    def test_incidents_search_param_filters_server_side(self) -> None:
        _, _, body = self._get("/api/incidents?window=24h&q=traffic")
        rows = json.loads(body)
        self.assertEqual([r["cad_number"] for r in rows], ["api-1"])
        _, _, body = self._get("/api/incidents?window=24h&q=nothingmatches")
        self.assertEqual(json.loads(body), [])
        # Search still respects Skip noise - turn it off to find routine calls.
        _, _, body = self._get("/api/incidents?window=24h&q=passing&hide_routine=0")
        rows = json.loads(body)
        self.assertEqual([r["cad_number"] for r in rows], ["api-pass"])

    def test_search_scopes_stats_and_heatmap_endpoints(self) -> None:
        # All three endpoints accept q, so every panel shows the same scope.
        _, _, body = self._get("/api/stats?window=24h&q=traffic")
        s = json.loads(body)
        self.assertEqual(s["total"], 1)
        _, _, body = self._get("/api/heatmap?window=24h&q=traffic")
        self.assertEqual(len(json.loads(body)["points"]), 1)
        _, _, body = self._get("/api/stats?window=24h&q=nothingmatches")
        self.assertEqual(json.loads(body)["total"], 0)

    def test_incidents_hide_routine_by_default(self) -> None:
        _, _, body = self._get("/api/incidents?window=24h")
        rows = json.loads(body)
        ids = {row["cad_number"] for row in rows}
        self.assertIn("api-1", ids)
        self.assertNotIn("api-pass", ids)

    def test_heatmap_and_stats_include_traffic_stops(self) -> None:
        _, _, heat_body = self._get("/api/heatmap?window=24h")
        heat = json.loads(heat_body)
        self.assertTrue(heat["points"])
        _, _, stats_body = self._get("/api/stats?window=24h")
        stats = json.loads(stats_body)
        self.assertGreaterEqual(stats["total"], 1)
        self.assertEqual(stats["hotspots"][0]["n"], 1)

    def test_meta_includes_90d_window(self) -> None:
        _, _, body = self._get("/api/meta")
        meta = json.loads(body)
        self.assertIn("90d", meta["windows"])
        self.assertEqual(meta["windows"][-1], "90d")

    def test_meta_lists_basemaps_with_an_offline_option(self) -> None:
        _, _, body = self._get("/api/meta")
        meta = json.loads(body)
        ids = [row["id"] for row in meta["basemaps"]]
        self.assertIn("none", ids)
        self.assertIn("esri-dark", ids)
        self.assertEqual(set(meta["basemap"]), {"id", "label", "url", "subdomains", "attribution"})

    @patch.dict("os.environ", {"SFALERT_BASEMAP": "none"})
    def test_meta_honors_env_basemap(self) -> None:
        _, _, body = self._get("/api/meta")
        meta = json.loads(body)
        self.assertEqual(meta["basemap"]["id"], "none")
        self.assertIsNone(meta["basemap"]["url"])

    def test_unknown_window_is_400(self) -> None:
        with self.assertRaises(HTTPError) as ctx:
            urlopen(self.base + "/api/incidents?window=5min", timeout=5)
        self.assertEqual(ctx.exception.code, 400)

    def test_non_integer_limit_is_400(self) -> None:
        with self.assertRaises(HTTPError) as ctx:
            urlopen(self.base + "/api/incidents?limit=abc", timeout=5)
        self.assertEqual(ctx.exception.code, 400)

    def test_limit_is_clamped(self) -> None:
        _, _, body = self._get("/api/incidents?limit=100000")
        self.assertLessEqual(len(json.loads(body)), 500)

    @patch("sfalert.ingest.ingest", return_value={"realtime": 1, "total": 2})
    def test_refresh_is_rate_limited(self, ingest) -> None:
        import time as real_time

        import sfalert.server as srv

        def post() -> int:
            req = Request(self.base + "/api/refresh", method="POST")
            with urlopen(req, timeout=5) as resp:
                return resp.status

        def expect_429() -> None:
            try:
                post()
                self.fail("expected 429")
            except HTTPError as err:
                try:
                    self.assertEqual(err.code, 429)
                finally:
                    err.close()

        srv._last_refresh = real_time.time() - 100  # state shared with other tests
        self.assertEqual(post(), 200)
        ingest.assert_called_once()

        expect_429()  # inside the 15s window

        srv._last_refresh = real_time.time() - 20  # window has passed
        self.assertEqual(post(), 200)

    @patch("sfalert.ingest.ingest", side_effect=RuntimeError("feed down"))
    def test_refresh_failure_is_500_and_hides_detail(self, _ingest) -> None:
        import time as real_time

        import sfalert.server as srv

        srv._last_refresh = real_time.time() - 100  # clear the rate limit
        req = Request(self.base + "/api/refresh", method="POST")
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req, timeout=5)
        err = ctx.exception
        try:
            self.assertEqual(err.code, 500)
            payload = json.loads(err.read())
        finally:
            err.close()
        self.assertEqual(payload["error"], "refresh failed")
        self.assertNotIn("feed down", payload["error"])

    def test_unknown_post_path_is_404(self) -> None:
        req = Request(self.base + "/api/nope", method="POST")
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 404)

    def test_unknown_api_is_404(self) -> None:
        with self.assertRaises(HTTPError) as ctx:
            urlopen(self.base + "/api/nope", timeout=5)
        err = ctx.exception
        self.assertEqual(err.code, 404)
        try:
            payload = json.loads(err.read())
        finally:
            err.close()
        self.assertEqual(payload["error"], "not found")

    @patch("sfalert.server.list_incidents", side_effect=RuntimeError("secret detail"))
    def test_500_response_hides_internals(self, _list_incidents) -> None:
        req = Request(self.base + "/api/incidents", method="GET")
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req, timeout=5)
        err = ctx.exception
        try:
            self.assertEqual(err.code, 500)
            payload = json.loads(err.read())
        finally:
            err.close()
        self.assertEqual(payload["error"], "internal server error")
        self.assertNotIn("secret detail", payload["error"])

    @patch("sfalert.ingest.ingest", return_value={"realtime": 1, "total": 2})
    def test_refresh_posts_to_ingest(self, ingest) -> None:
        # The limiter keeps module-level state; reset so this test is
        # independent of test ordering.
        import time as real_time

        import sfalert.server as srv

        srv._last_refresh = real_time.time() - 100
        req = Request(self.base + "/api/refresh", method="POST")
        with urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read())
        self.assertEqual(payload["realtime"], 1)
        ingest.assert_called_once()


class ServeTest(unittest.TestCase):
    @patch("sfalert.server.ThreadingHTTPServer.serve_forever", side_effect=KeyboardInterrupt)
    def test_serve_stops_cleanly_on_interrupt(self, _forever) -> None:
        serve(host="127.0.0.1", port=0, poll=False)  # must not raise

    @patch("sfalert.ingest.ingest")
    @patch(
        "sfalert.server.ThreadingHTTPServer.serve_forever", side_effect=KeyboardInterrupt
    )
    def test_serve_starts_and_stops_the_poll_thread(self, _forever, ingest) -> None:
        # stop is set in serve()'s finally block before the poll thread ever
        # waits out its interval, so no ingest may happen.
        serve(host="127.0.0.1", port=0, poll=True)
        ingest.assert_not_called()

    def test_poll_forever_ingests_each_tick_and_swallows_errors(self) -> None:
        import sfalert.server as srv

        class TwoTicksEvent:
            """Stands in for threading.Event: False, False, then True."""

            def __init__(self) -> None:
                self.waits = 0

            def wait(self, timeout: float) -> bool:
                self.waits += 1
                return self.waits > 2

            def set(self) -> None:
                return None

        with patch.object(srv, "ingest_mod") as ingest_mod:
            ingest_mod.ingest.side_effect = [None, RuntimeError("feed down")]
            srv._poll_forever(TwoTicksEvent())
        self.assertEqual(ingest_mod.ingest.call_count, 2)
