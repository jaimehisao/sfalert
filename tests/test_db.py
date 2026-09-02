import tempfile
import unittest
from pathlib import Path

from sfalert.db import connect, count_incidents, upsert_incidents

from tests.helpers import incident_row


class SqliteStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sfalert.db"
        self.conn = connect(self.path)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_creates_incidents_table(self) -> None:
        tables = {
            row[0]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertIn("incidents", tables)

    def test_upsert_inserts_and_counts(self) -> None:
        n = upsert_incidents(self.conn, [incident_row(), incident_row(cad_number="1002")])
        self.assertEqual(n, 2)
        self.assertEqual(count_incidents(self.conn), 2)

    def test_upsert_updates_status_by_cad_number(self) -> None:
        upsert_incidents(self.conn, [incident_row(status="open", close_datetime=None)])
        upsert_incidents(
            self.conn,
            [
                incident_row(
                    status="closed",
                    close_datetime="2026-09-02T11:00:00.000",
                    source="closed",
                )
            ],
        )
        row = self.conn.execute(
            "SELECT status, close_datetime, source FROM incidents WHERE cad_number='1001'"
        ).fetchone()
        self.assertEqual(row["status"], "closed")
        self.assertEqual(row["source"], "closed")
        self.assertIsNotNone(row["close_datetime"])

    def test_upsert_keeps_existing_coordinates_when_new_row_has_none(self) -> None:
        upsert_incidents(self.conn, [incident_row(lat=37.78, lon=-122.41)])
        upsert_incidents(
            self.conn,
            [incident_row(lat=None, lon=None, intersection=None, status="closed")],
        )
        row = self.conn.execute(
            "SELECT lat, lon, intersection, status FROM incidents WHERE cad_number='1001'"
        ).fetchone()
        self.assertAlmostEqual(row["lat"], 37.78)
        self.assertAlmostEqual(row["lon"], -122.41)
        self.assertEqual(row["intersection"], "MARKET ST \\ 6TH ST")
        self.assertEqual(row["status"], "closed")

    def test_connect_is_idempotent_on_existing_file(self) -> None:
        upsert_incidents(self.conn, [incident_row()])
        self.conn.close()
        again = connect(self.path)
        try:
            self.assertEqual(count_incidents(again), 1)
        finally:
            again.close()
