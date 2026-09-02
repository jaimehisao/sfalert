import json
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import URLError

from sfalert.fetch import (
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

    @patch("sfalert.fetch.soda_get")
    def test_iter_closed_paginates(self, soda_get_mock) -> None:
        soda_get_mock.side_effect = [[{"cad_number": "a"}] * 2, []]
        with patch("sfalert.fetch.PAGE_SIZE", 2):
            batches = list(iter_closed(days=1))
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]), 2)

    @patch("sfalert.fetch.soda_get")
    def test_fetch_realtime_stops_on_short_page(self, soda_get_mock) -> None:
        soda_get_mock.return_value = [{"cad_number": "1"}]
        rows = fetch_realtime()
        self.assertEqual(len(rows), 1)
        soda_get_mock.assert_called_once()

    def test_iso_days_ago_format(self) -> None:
        stamp = iso_days_ago(7)
        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}T00:00:00$")
