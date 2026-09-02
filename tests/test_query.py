import tempfile
import unittest
from pathlib import Path

from sfalert.db import connect, upsert_incidents
from sfalert.query import heatmap_points, list_incidents, stats, window_start

from tests.helpers import incident_row, pacific_iso


class QueryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self.tmp.name) / "sfalert.db")
        upsert_incidents(
            self.conn,
            [
                incident_row(
                    cad_number="stop-1",
                    call_type_final_desc="TRAFFIC STOP",
                    category="traffic",
                    routine=0,
                    severity=4,
                    lat=37.78,
                    lon=-122.41,
                    intersection="MARKET ST \\ 6TH ST",
                    received_datetime=pacific_iso(hours=2),
                    status="open",
                ),
                incident_row(
                    cad_number="stop-2",
                    call_type_final_desc="TRAFFIC STOP",
                    category="traffic",
                    routine=0,
                    severity=4,
                    lat=37.78,
                    lon=-122.41,
                    intersection="MARKET ST \\ 6TH ST",
                    received_datetime=pacific_iso(hours=1),
                    status="closed",
                    close_datetime=pacific_iso(hours=1),
                ),
                incident_row(
                    cad_number="pass-1",
                    call_type_final_desc="PASSING CALL",
                    category="other",
                    routine=1,
                    severity=1,
                    lat=37.76,
                    lon=-122.43,
                    intersection="HAIGHT ST \\ ASHBURY ST",
                    neighborhood="Haight Ashbury",
                    district="PARK",
                    received_datetime=pacific_iso(hours=1),
                    status="closed",
                ),
                incident_row(
                    cad_number="old-1",
                    call_type_final_desc="ASSAULT / BATTERY",
                    category="violence",
                    routine=0,
                    severity=5,
                    lat=37.78,
                    lon=-122.41,
                    received_datetime=pacific_iso(days=10),
                    status="closed",
                ),
            ],
        )

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_window_start_is_ordered(self) -> None:
        self.assertGreater(window_start("3h"), window_start("24h"))
        self.assertGreater(window_start("24h"), window_start("7d"))

    def test_hide_routine_keeps_traffic_stops_out_of_passing_calls(self) -> None:
        hidden = list_incidents(self.conn, window="24h", hide_routine=True)
        shown = {row["cad_number"] for row in hidden}
        self.assertIn("stop-1", shown)
        self.assertIn("stop-2", shown)
        self.assertNotIn("pass-1", shown)
        self.assertNotIn("old-1", shown)

        all_rows = list_incidents(self.conn, window="24h", hide_routine=False)
        all_ids = {row["cad_number"] for row in all_rows}
        self.assertIn("pass-1", all_ids)

    def test_heatmap_includes_traffic_stops_and_skips_routine(self) -> None:
        points = heatmap_points(self.conn, window="24h", hide_routine=True)
        self.assertEqual(len(points), 1)
        lat, lon, intensity = points[0]
        self.assertAlmostEqual(lat, 37.78, places=2)
        self.assertAlmostEqual(lon, -122.41, places=2)
        self.assertGreater(intensity, 0)

        with_noise = heatmap_points(self.conn, window="24h", hide_routine=False)
        self.assertEqual(len(with_noise), 2)

    def test_stats_hotspots_rank_stop_intersection(self) -> None:
        result = stats(self.conn, window="24h", hide_routine=True)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["open"], 1)
        self.assertEqual(result["mapped"], 2)
        self.assertEqual(result["hotspots"][0]["intersection"], "MARKET ST \\ 6TH ST")
        self.assertEqual(result["hotspots"][0]["n"], 2)
        cats = {row["category"]: row["n"] for row in result["by_category"]}
        self.assertEqual(cats.get("traffic"), 2)
        self.assertNotIn("other", cats)

    def test_category_and_district_filters(self) -> None:
        rows = list_incidents(
            self.conn, window="30d", category="violence", hide_routine=True
        )
        self.assertEqual([row["cad_number"] for row in rows], ["old-1"])
        southern = list_incidents(
            self.conn, window="24h", district="SOUTHERN", hide_routine=True
        )
        self.assertTrue(southern)
        self.assertTrue(all(row["district"] == "SOUTHERN" for row in southern))
