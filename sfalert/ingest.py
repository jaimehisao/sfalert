from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .db import connect, count_incidents, upsert_incidents
from .fetch import fetch_realtime, iter_closed, normalize

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ingest(
    days: int = 30,
    realtime: bool = True,
    backfill: bool = True,
    log: Callable[[str], None] = print,
    db_path: Path | None = None,
) -> dict[str, int]:
    """Pull CAD into SQLite. Safe to call repeatedly (upserts by cad_number)."""
    with _lock:
        conn = connect(db_path)
        ingested_at = _now()
        closed_n = 0
        live_n = 0
        try:
            if backfill:
                log(f"Backfilling closed CAD calls for the last {days} day(s)...")
                for batch in iter_closed(days):
                    rows = [normalize(row, "closed", ingested_at) for row in batch]
                    rows = [row for row in rows if row["cad_number"]]
                    closed_n += upsert_incidents(conn, rows)
                    log(f"  closed upserted {closed_n:,}")
            if realtime:
                log("Fetching real-time CAD window (last ~48h)...")
                live = fetch_realtime()
                rows = [normalize(row, "realtime", ingested_at) for row in live]
                rows = [row for row in rows if row["cad_number"]]
                live_n = upsert_incidents(conn, rows)
                log(f"  realtime upserted {live_n:,}")
            total = count_incidents(conn)
            log(f"Done. Local store has {total:,} incidents.")
            return {"closed": closed_n, "realtime": live_n, "total": total}
        finally:
            conn.close()


def ensure_data(
    days: int = 30,
    log: Callable[[str], None] = print,
    db_path: Path | None = None,
) -> dict[str, int]:
    conn = connect(db_path)
    try:
        n = count_incidents(conn)
    finally:
        conn.close()
    if n == 0:
        log("Empty database — running first ingest.")
        return ingest(days=days, realtime=True, backfill=True, log=log, db_path=db_path)
    log(f"Database already has {n:,} incidents — refreshing real-time feed.")
    return ingest(days=days, realtime=True, backfill=False, log=log, db_path=db_path)
