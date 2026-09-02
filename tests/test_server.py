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
from sfalert.server import Handler

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
        status, _, js = self._get("/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"heatmap", js)

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

    @patch("sfalert.ingest.ingest", return_value={"realtime": 1, "total": 2})
    def test_refresh_posts_to_ingest(self, ingest) -> None:
        req = Request(self.base + "/api/refresh", method="POST")
        with urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read())
        self.assertEqual(payload["realtime"], 1)
        ingest.assert_called_once()
