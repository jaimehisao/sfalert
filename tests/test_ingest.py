import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sfalert.db import connect, count_incidents, prune_incidents
from sfalert.ingest import ensure_data, ingest

from tests.helpers import cad_payload, incident_row, pacific_iso


class IngestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sfalert.db"
        self.logs: list[str] = []

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _log(self, msg: str) -> None:
        self.logs.append(msg)

    @patch("sfalert.ingest.fetch_realtime", return_value=[])
    @patch("sfalert.ingest.iter_closed")
    def test_backfill_writes_normalized_rows(self, iter_closed, _realtime) -> None:
        iter_closed.return_value = [
            [cad_payload(), cad_payload(cad_number="262450002")]
        ]
        result = ingest(
            days=2,
            realtime=False,
            backfill=True,
            log=self._log,
            db_path=self.path,
        )
        self.assertEqual(result["closed"], 2)
        self.assertEqual(result["total"], 2)
        conn = connect(self.path)
        try:
            row = conn.execute(
                "SELECT category, routine FROM incidents WHERE cad_number='262450001'"
            ).fetchone()
            self.assertEqual(row["category"], "traffic")
            self.assertEqual(row["routine"], 0)
        finally:
            conn.close()

    @patch("sfalert.ingest.iter_closed")
    @patch("sfalert.ingest.fetch_realtime")
    def test_realtime_updates_open_to_closed(self, fetch_realtime, iter_closed) -> None:
        iter_closed.return_value = []
        open_row = cad_payload(cad_number="9", close_datetime="")
        closed_row = cad_payload(cad_number="9", close_datetime="2026-09-02T12:00:00.000")
        fetch_realtime.side_effect = [[open_row], [closed_row]]
        ingest(realtime=True, backfill=False, log=self._log, db_path=self.path)
        ingest(realtime=True, backfill=False, log=self._log, db_path=self.path)
        conn = connect(self.path)
        try:
            row = conn.execute(
                "SELECT status, close_datetime FROM incidents WHERE cad_number='9'"
            ).fetchone()
            self.assertEqual(row["status"], "closed")
            self.assertTrue(row["close_datetime"])
            self.assertEqual(count_incidents(conn), 1)
        finally:
            conn.close()

    @patch("sfalert.ingest.fetch_realtime", return_value=[cad_payload()])
    @patch("sfalert.ingest.iter_closed", return_value=[])
    def test_ensure_data_backfills_empty_then_only_refreshes(self, iter_closed, _rt) -> None:
        ensure_data(days=1, log=self._log, db_path=self.path)
        self.assertTrue(any("Empty database" in line for line in self.logs))
        self.logs.clear()
        iter_closed.return_value = [[cad_payload(cad_number="should-not-write")]]
        ensure_data(days=1, log=self._log, db_path=self.path)
        self.assertTrue(any("already has" in line for line in self.logs))
        conn = connect(self.path)
        try:
            cad_numbers = {
                row[0] for row in conn.execute("SELECT cad_number FROM incidents")
            }
            self.assertNotIn("should-not-write", cad_numbers)
        finally:
            conn.close()

    @patch("sfalert.ingest.fetch_realtime", return_value=[cad_payload(cad_number="  ")])
    @patch("sfalert.ingest.iter_closed", return_value=[[[]]])
    def test_skips_rows_without_cad_number(self, _closed, _rt) -> None:
        result = ingest(backfill=False, realtime=True, log=self._log, db_path=self.path)
        self.assertEqual(result["realtime"], 0)
        self.assertEqual(result["total"], 0)

    def test_prune_deletes_old_and_keeps_fts_in_step(self) -> None:
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo("America/Los_Angeles"))
        old_dt = (now - timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%S")
        new_dt = pacific_iso(hours=1)
        conn = connect(self.path)
        try:
            from sfalert.db import upsert_incidents

            upsert_incidents(
                conn,
                [
                    incident_row(
                        cad_number="old-9", received_datetime=old_dt,
                        call_type_final_desc="OLD CALL MARKERXYZ",
                    ),
                    incident_row(cad_number="new-9", received_datetime=new_dt),
                ],
            )
            self.assertEqual(count_incidents(conn), 2)
            deleted = prune_incidents(conn, 90)
            self.assertEqual(deleted, 1)
            remaining = {
                row[0] for row in conn.execute("SELECT cad_number FROM incidents")
            }
            self.assertEqual(remaining, {"new-9"})
            fts = {
                row[0]
                for row in conn.execute("SELECT cad_number FROM incidents_fts")
            }
            self.assertEqual(fts, {"new-9"})
        finally:
            conn.close()

    def test_prune_rejects_non_positive_days(self) -> None:
        conn = connect(self.path)
        try:
            with self.assertRaises(ValueError):
                prune_incidents(conn, 0)
        finally:
            conn.close()

    @patch("sfalert.ingest.fetch_realtime", return_value=[])
    @patch("sfalert.ingest.iter_closed", return_value=[])
    def test_ingest_with_prune_days_reports_pruned(self, _closed, _rt) -> None:
        conn = connect(self.path)
        try:
            from datetime import datetime, timedelta
            from zoneinfo import ZoneInfo

            from sfalert.db import upsert_incidents

            now = datetime.now(ZoneInfo("America/Los_Angeles"))
            old_dt = (now - timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%S")
            upsert_incidents(conn, [incident_row(received_datetime=old_dt)])
        finally:
            conn.close()
        result = ingest(
            backfill=False, realtime=False, log=self._log,
            db_path=self.path, prune_days=90,
        )
        self.assertEqual(result["pruned"], 1)
        self.assertEqual(result["total"], 0)
