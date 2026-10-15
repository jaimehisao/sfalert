import json
import os
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from sfalert.fetch import (
    _headers,
    _truthy,
    fetch_realtime,
    iso_days_ago,
    iter_closed,
    normalize,
    soda_get,
)

from tests.helpers import cad_payload


class FakeResponse:
    def __init__(self, payload):
        raw = json.dumps(payload).encode("utf-8")
        self._buf = BytesIO(raw)

    def read(self) -> bytes:
        return self._buf.read()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> None:
        return None


class NormalizeTest(unittest.TestCase):
    def test_geojson_point_and_closed_status(self) -> None:
        row = normalize(cad_payload(), "closed", "2026-09-02T18:00:00Z")
        self.assertEqual(row["cad_number"], "262450001")
        self.assertEqual(row["status"], "closed")
        self.assertEqual(row["category"], "traffic")
        self.assertEqual(row["routine"], 0)
        self.assertAlmostEqual(row["lat"], 37.782)
        self.assertAlmostEqual(row["lon"], -122.41)
        self.assertEqual(row["onview"], 1)

    def test_open_when_close_datetime_missing(self) -> None:
        row = normalize(cad_payload(close_datetime=""), "realtime", "t")
        self.assertEqual(row["status"], "open")
        self.assertIsNone(row["close_datetime"])

    def test_wkt_point(self) -> None:
        row = normalize(
            cad_payload(intersection_point="POINT (-122.4194 37.7749)"),
            "closed",
            "t",
        )
        self.assertAlmostEqual(row["lat"], 37.7749)
        self.assertAlmostEqual(row["lon"], -122.4194)

    def test_rejects_coordinates_outside_sf(self) -> None:
        row = normalize(
            cad_payload(intersection_point={"type": "Point", "coordinates": [0, 0]}),
            "closed",
            "t",
        )
        self.assertIsNone(row["lat"])
        self.assertIsNone(row["lon"])

    def test_wkt_point_outside_sf_is_rejected(self) -> None:
        # The WKT branch used to skip the bounds check the GeoJSON branch has.
        row = normalize(
            cad_payload(intersection_point="POINT (0 0)"), "closed", "t"
        )
        self.assertIsNone(row["lat"])
        self.assertIsNone(row["lon"])

    def test_malformed_points_do_not_raise(self) -> None:
        # A single garbage row must degrade to unmapped, not kill the batch.
        for point in (
            {"type": "Point"},
            {"coordinates": ["abc", "def"]},
            {"coordinates": [-122.41]},
            "POINT",
            "POINT (abc def)",
            12345,
            None,
        ):
            row = normalize(
                cad_payload(intersection_point=point), "closed", "t"
            )
            self.assertIsNone(row["lat"], point)
            self.assertIsNone(row["lon"], point)

    def test_passing_call_is_routine(self) -> None:
        row = normalize(
            cad_payload(
                call_type_final_desc="PASSING CALL",
                call_type_original_desc="PASSING CALL",
            ),
            "realtime",
            "t",
        )
        self.assertEqual(row["routine"], 1)


    def test_truthy_handles_flag_values(self) -> None:
        for value in (True, 1, "true", "Y", "YES", "1"):
            self.assertEqual(_truthy(value), 1, value)
        for value in (False, 0, None, "N", "", "0", "n"):
            self.assertEqual(_truthy(value), 0, value)


class SodaClientTest(unittest.TestCase):
    @patch("sfalert.fetch.urllib.request.urlopen")
    def test_soda_get_parses_list(self, urlopen) -> None:
        urlopen.return_value = FakeResponse([{"cad_number": "1"}])
        rows = soda_get("https://example.test/data.json", {"$limit": "1"})
        self.assertEqual(rows, [{"cad_number": "1"}])
        urlopen.assert_called_once()

    @patch("sfalert.fetch.time.sleep")
    @patch("sfalert.fetch.urllib.request.urlopen")
    def test_soda_get_retries_then_fails(self, urlopen, sleep) -> None:
        urlopen.side_effect = URLError("down")
        with self.assertRaises(RuntimeError):
            soda_get("https://example.test/data.json", {}, retries=3)
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual(sleep.call_count, 3)

    @patch("sfalert.fetch.time.sleep")
    @patch("sfalert.fetch.urllib.request.urlopen")
    def test_soda_get_does_not_retry_client_errors(self, urlopen, sleep) -> None:
        # HTTPError subclasses URLError; a 400 will never succeed on retry.
        urlopen.side_effect = HTTPError("https://x.test", 400, "Bad Request", {}, None)
        with self.assertRaises(RuntimeError):
            soda_get("https://example.test/data.json", {}, retries=4)
        self.assertEqual(urlopen.call_count, 1)
        sleep.assert_not_called()

    @patch("sfalert.fetch.time.sleep")
    @patch("sfalert.fetch.urllib.request.urlopen")
    def test_soda_get_retries_then_succeeds_on_429(self, urlopen, sleep) -> None:
        urlopen.side_effect = [
            HTTPError("https://x.test", 429, "Too Many Requests", {}, None),
            FakeResponse([{"cad_number": "1"}]),
        ]
        rows = soda_get("https://example.test/data.json", {})
        self.assertEqual(rows, [{"cad_number": "1"}])
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once()

    @patch.dict(os.environ, {"SFALERT_APP_TOKEN": "tok123"})
    def test_headers_include_app_token(self) -> None:
        self.assertEqual(_headers()["X-App-Token"], "tok123")

    @patch.dict(os.environ, {}, clear=True)
    def test_headers_without_token(self) -> None:
        self.assertNotIn("X-App-Token", _headers())

    @patch("sfalert.fetch.soda_get")
    def test_iter_closed_stops_on_empty_first_page(self, soda_get_mock) -> None:
        soda_get_mock.return_value = []
        with patch("sfalert.fetch.PAGE_SIZE", 2):
            self.assertEqual(list(iter_closed(days=1)), [])

    @patch("sfalert.fetch.soda_get")
    def test_iter_closed_paginates(self, soda_get_mock) -> None:
        # page1 is full (== patched PAGE_SIZE) so iteration continues;
        # page2 is short, which ends the stream.
        soda_get_mock.side_effect = [
            [{"cad_number": "a"}, {"cad_number": "b"}],
            [{"cad_number": "c"}],
        ]
        with patch("sfalert.fetch.PAGE_SIZE", 2):
            batches = list(iter_closed(days=1))
        self.assertEqual([len(b) for b in batches], [2, 1])

    @patch("sfalert.fetch.soda_get")
    def test_fetch_realtime_stops_on_short_page(self, soda_get_mock) -> None:
        soda_get_mock.return_value = [{"cad_number": "1"}]
        rows = fetch_realtime()
        self.assertEqual(len(rows), 1)
        soda_get_mock.assert_called_once()

    @patch("sfalert.fetch.soda_get")
    def test_fetch_realtime_paginates_full_pages(self, soda_get_mock) -> None:
        full_page = [{"cad_number": str(i)} for i in range(50000)]
        soda_get_mock.side_effect = [full_page, []]
        rows = fetch_realtime()
        self.assertEqual(len(rows), 50000)
        self.assertEqual(soda_get_mock.call_count, 2)

    @patch("sfalert.fetch.time.sleep")
    @patch("sfalert.fetch.urllib.request.urlopen")
    def test_soda_get_rejects_socrata_error_payload(self, urlopen, _sleep) -> None:
        # A fresh response per attempt: error payloads are retried, and a
        # reused BytesIO would be exhausted by then.
        urlopen.side_effect = lambda *a, **k: FakeResponse(
            {"error": True, "message": "query too big"}
        )
        with self.assertRaises(RuntimeError):
            soda_get("https://example.test/data.json", {})
        self.assertEqual(urlopen.call_count, 4)

    @patch("sfalert.fetch.time.sleep")
    @patch("sfalert.fetch.urllib.request.urlopen")
    def test_soda_get_rejects_non_list_payload(self, urlopen, _sleep) -> None:
        urlopen.side_effect = lambda *a, **k: FakeResponse({"not": "a list"})
        with self.assertRaises(RuntimeError):
            soda_get("https://example.test/data.json", {})
        self.assertEqual(urlopen.call_count, 4)

    def test_iso_days_ago_format(self) -> None:
        stamp = iso_days_ago(7)
        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}T00:00:00$")
