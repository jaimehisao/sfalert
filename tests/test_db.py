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
        self.assertEqual(SCHEMA_VERSION, 3)

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
        self.conn.execute("DROP TABLE IF EXISTS incidents_fts")
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

    def test_fts_table_and_triggers_exist(self) -> None:
        tables = {
            row[0]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertIn("incidents_fts", tables)
        triggers = {
            row[0]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
        self.assertIn("incidents_fts_ai", triggers)
        self.assertIn("incidents_fts_ad", triggers)
        self.assertIn("incidents_fts_au", triggers)

    def test_fts_syncs_on_upsert_and_update(self) -> None:
        upsert_incidents(self.conn, [incident_row(cad_number="fts-1")])
        rows = list(
            self.conn.execute(
                "SELECT cad_number FROM incidents_fts WHERE incidents_fts MATCH ?",
                ('"traffic"',),
            )
        )
        self.assertEqual([r[0] for r in rows], ["fts-1"])
        # Update via upsert keeps FTS in step (trigger fires on conflict).
        row = incident_row(
            cad_number="fts-1", call_type_final_desc="ASSAULT / BATTERY"
        )
        upsert_incidents(self.conn, [row])
        old = list(
            self.conn.execute(
                "SELECT cad_number FROM incidents_fts WHERE incidents_fts MATCH ?",
                ('"traffic"',),
            )
        )
        self.assertEqual(old, [])
        new = list(
            self.conn.execute(
                "SELECT cad_number FROM incidents_fts WHERE incidents_fts MATCH ?",
                ('"assault"',),
            )
        )
        self.assertEqual([r[0] for r in new], ["fts-1"])

    def test_v2_database_backfills_fts(self) -> None:
        # Rows written before the v3 triggers must become searchable.
        self.conn.execute("DELETE FROM incidents_fts")
        self.conn.execute("DROP TRIGGER IF EXISTS incidents_fts_ai")
        self.conn.execute("DROP TRIGGER IF EXISTS incidents_fts_au")
        self.conn.execute("DROP TRIGGER IF EXISTS incidents_fts_ad")
        upsert_incidents(self.conn, [incident_row(cad_number="backfill-1")])
        self.assertEqual(
            list(self.conn.execute("SELECT COUNT(*) FROM incidents_fts"))[0][0],
            0,
        )
        self.conn.execute("PRAGMA user_version = 2")
        self.conn.commit()
        self.conn.close()
        migrated = connect(self.path)
        try:
            found = list(
                migrated.execute(
                    "SELECT cad_number FROM incidents_fts "
                    "WHERE incidents_fts MATCH ?",
                    ('"traffic"',),
                )
            )
            self.assertEqual([r[0] for r in found], ["backfill-1"])
        finally:
            migrated.close()
        self.conn = connect(self.path)

    def test_connect_sets_busy_timeout(self) -> None:
        timeout = self.conn.execute("PRAGMA busy_timeout").fetchone()[0]
        self.assertGreaterEqual(timeout, 1000)
