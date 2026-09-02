from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "sfalert.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    cad_number TEXT PRIMARY KEY,
    received_datetime TEXT,
    dispatch_datetime TEXT,
    onscene_datetime TEXT,
    close_datetime TEXT,
    call_last_updated_at TEXT,
    call_type TEXT,
    call_type_desc TEXT,
    call_type_final TEXT,
    call_type_final_desc TEXT,
    priority TEXT,
    agency TEXT,
    disposition TEXT,
    onview INTEGER,
    sensitive INTEGER,
    intersection TEXT,
    lat REAL,
    lon REAL,
    neighborhood TEXT,
    district TEXT,
    supervisor_district TEXT,
    pd_incident_report TEXT,
    category TEXT NOT NULL,
    routine INTEGER NOT NULL DEFAULT 0,
    severity INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    source TEXT,
    ingested_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_incidents_received ON incidents(received_datetime);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_category ON incidents(category);
CREATE INDEX IF NOT EXISTS idx_incidents_district ON incidents(district);
CREATE INDEX IF NOT EXISTS idx_incidents_geo ON incidents(lat, lon);
CREATE INDEX IF NOT EXISTS idx_incidents_routine ON incidents(routine);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def count_incidents(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM incidents").fetchone()
    return int(row["n"]) if row else 0


def upsert_incidents(conn: sqlite3.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO incidents (
        cad_number, received_datetime, dispatch_datetime, onscene_datetime,
        close_datetime, call_last_updated_at, call_type, call_type_desc,
        call_type_final, call_type_final_desc, priority, agency, disposition,
        onview, sensitive, intersection, lat, lon, neighborhood, district,
        supervisor_district, pd_incident_report, category, routine, severity,
        status, source, ingested_at
    ) VALUES (
        :cad_number, :received_datetime, :dispatch_datetime, :onscene_datetime,
        :close_datetime, :call_last_updated_at, :call_type, :call_type_desc,
        :call_type_final, :call_type_final_desc, :priority, :agency, :disposition,
        :onview, :sensitive, :intersection, :lat, :lon, :neighborhood, :district,
        :supervisor_district, :pd_incident_report, :category, :routine, :severity,
        :status, :source, :ingested_at
    )
    ON CONFLICT(cad_number) DO UPDATE SET
        received_datetime=excluded.received_datetime,
        dispatch_datetime=excluded.dispatch_datetime,
        onscene_datetime=excluded.onscene_datetime,
        close_datetime=excluded.close_datetime,
        call_last_updated_at=excluded.call_last_updated_at,
        call_type=excluded.call_type,
        call_type_desc=excluded.call_type_desc,
        call_type_final=excluded.call_type_final,
        call_type_final_desc=excluded.call_type_final_desc,
        priority=excluded.priority,
        agency=excluded.agency,
        disposition=excluded.disposition,
        onview=excluded.onview,
        sensitive=excluded.sensitive,
        intersection=COALESCE(excluded.intersection, incidents.intersection),
        lat=COALESCE(excluded.lat, incidents.lat),
        lon=COALESCE(excluded.lon, incidents.lon),
        neighborhood=COALESCE(excluded.neighborhood, incidents.neighborhood),
        district=COALESCE(excluded.district, incidents.district),
        supervisor_district=COALESCE(excluded.supervisor_district, incidents.supervisor_district),
        pd_incident_report=COALESCE(excluded.pd_incident_report, incidents.pd_incident_report),
        category=excluded.category,
        routine=excluded.routine,
        severity=excluded.severity,
        status=excluded.status,
        source=excluded.source,
        ingested_at=excluded.ingested_at
    """
    conn.executemany(sql, rows)
    conn.commit()
    return len(rows)
