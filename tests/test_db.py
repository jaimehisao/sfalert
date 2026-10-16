import tempfile
import unittest
from pathlib import Path

from sfalert.db import SCHEMA_VERSION, connect, count_incidents, upsert_incidents

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

    def test_connect_sets_schema_version(self) -> None:
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, SCHEMA_VERSION)
        self.assertEqual(SCHEMA_VERSION, 2)

    def test_composite_and_hotspot_indexes_exist(self) -> None:
        indexes = {
            row[0]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        self.assertIn("idx_incidents_filter", indexes)
        self.assertIn("idx_incidents_hotspot", indexes)

    def test_v1_database_migrates_to_v2_indexes(self) -> None:
        # Simulate a v1 store: drop the v2 indexes, stamp version 1.
        self.conn.execute("DROP INDEX IF EXISTS idx_incidents_filter")
        self.conn.execute("DROP INDEX IF EXISTS idx_incidents_hotspot")
        self.conn.execute("PRAGMA user_version = 1")
        self.conn.commit()
        self.conn.close()
        migrated = connect(self.path)
        try:
            self.assertEqual(
                migrated.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )
            names = {
                row[0]
                for row in migrated.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                )
            }
            self.assertIn("idx_incidents_filter", names)
            self.assertIn("idx_incidents_hotspot", names)
            # Data survives the migration.
            upserted = upsert_incidents(migrated, [incident_row()])
            self.assertEqual(upserted, 1)
            self.assertEqual(count_incidents(migrated), 1)
        finally:
            migrated.close()
        self.conn = connect(self.path)

    def test_connect_sets_busy_timeout(self) -> None:
        timeout = self.conn.execute("PRAGMA busy_timeout").fetchone()[0]
        self.assertGreaterEqual(timeout, 1000)
