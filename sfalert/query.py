from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .categories import category_meta

PACIFIC = ZoneInfo("America/Los_Angeles")

WINDOWS = {
    "3h": 3 / 24,
    "6h": 6 / 24,
    "12h": 12 / 24,
    "24h": 1,
    "7d": 7,
    "30d": 30,
    "90d": 90,
}


def window_start(window: str) -> str:
    days = WINDOWS.get(window, 1)
    start = datetime.now(PACIFIC) - timedelta(days=days)
    return start.strftime("%Y-%m-%dT%H:%M:%S")


def _filters(
    window: str,
    category: str | None,
    district: str | None,
    hide_routine: bool,
    status: str | None,
) -> tuple[str, list[Any]]:
    clauses = ["received_datetime >= ?"]
    args: list[Any] = [window_start(window)]
    if category:
        clauses.append("category = ?")
        args.append(category)
    if district:
        clauses.append("district = ?")
        args.append(district)
    if hide_routine:
        clauses.append("routine = 0")
    if status in {"open", "closed"}:
        clauses.append("status = ?")
        args.append(status)
    return " AND ".join(clauses), args


_LIKE_COLUMNS = (
    "call_type_final_desc",
    "intersection",
    "neighborhood",
    "district",
    "cad_number",
    "agency",
)


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so user input is matched literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _search_clause(q: str | None) -> tuple[str, list[Any]]:
    """Build the search predicate shared by feed, heatmap, and stats.

    Returns a fragment to append to a WHERE clause (already ANDed) and its
    bind arguments, or empty pieces when q is unset.
    """
    if not q:
        return "", []
    like = f"%{_escape_like(q)}%"
    clauses = [f"{col} LIKE ? ESCAPE '\\'" for col in _LIKE_COLUMNS]
    return " AND (" + " OR ".join(clauses) + ")", [like] * len(_LIKE_COLUMNS)


def list_incidents(
    conn: sqlite3.Connection,
    window: str = "24h",
    category: str | None = None,
    district: str | None = None,
    hide_routine: bool = True,
    status: str | None = None,
    limit: int = 200,
    q: str | None = None,
) -> list[dict[str, Any]]:
    where, args = _filters(window, category, district, hide_routine, status)
    search_where, search_args = _search_clause(q)
    sql = f"""
        SELECT cad_number, received_datetime, dispatch_datetime, onscene_datetime,
               close_datetime, call_type_final_desc, priority, agency, intersection,
               lat, lon, neighborhood, district, category, routine, severity, status,
               sensitive, disposition
        FROM incidents
        WHERE {where}{search_where}
        ORDER BY received_datetime DESC
        LIMIT ?
    """
    rows = conn.execute(sql, [*args, *search_args, limit]).fetchall()
    return [dict(row) for row in rows]


def heatmap_points(
    conn: sqlite3.Connection,
    window: str = "24h",
    category: str | None = None,
    district: str | None = None,
    hide_routine: bool = True,
    q: str | None = None,
) -> list[list[float]]:
    where, args = _filters(window, category, district, hide_routine, None)
    search_where, search_args = _search_clause(q)
    sql = f"""
        SELECT ROUND(lat, 4) AS lat, ROUND(lon, 4) AS lon,
               COUNT(*) AS n, SUM(severity) AS weight
        FROM incidents
        WHERE {where}{search_where} AND lat IS NOT NULL AND lon IS NOT NULL
        GROUP BY ROUND(lat, 4), ROUND(lon, 4)
    """
    rows = list(conn.execute(sql, [*args, *search_args]))
    max_w = max((row["weight"] or 0) for row in rows) if rows else 1
    points = []
    for row in rows:
        intensity = (row["weight"] or 0) / max_w if max_w else 0
        points.append([row["lat"], row["lon"], round(max(intensity, 0.12), 3)])
    return points


def stats(
    conn: sqlite3.Connection,
    window: str = "24h",
    category: str | None = None,
    district: str | None = None,
    hide_routine: bool = True,
    q: str | None = None,
) -> dict[str, Any]:
    where, args = _filters(window, category, district, hide_routine, None)
    search_where, search_args = _search_clause(q)
    # Every aggregate below shares this WHERE, so a search scopes the
    # counts, chips, hour bars, and hotspots the same way it scopes the feed.
    where += search_where
    args = [*args, *search_args]
    total = conn.execute(
        f"SELECT COUNT(*) AS n FROM incidents WHERE {where}", args
    ).fetchone()["n"]
    open_n = conn.execute(
        f"SELECT COUNT(*) AS n FROM incidents WHERE {where} AND status='open'", args
    ).fetchone()["n"]
    mapped = conn.execute(
        f"SELECT COUNT(*) AS n FROM incidents WHERE {where} AND lat IS NOT NULL", args
    ).fetchone()["n"]

    by_cat = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT category, COUNT(*) AS n
            FROM incidents WHERE {where}
            GROUP BY category ORDER BY n DESC
            """,
            args,
        )
    ]
    by_hood = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT COALESCE(neighborhood, 'Unknown') AS neighborhood, COUNT(*) AS n
            FROM incidents WHERE {where}
            GROUP BY neighborhood ORDER BY n DESC LIMIT 8
            """,
            args,
        )
    ]
    by_hour = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT CAST(strftime('%H', received_datetime) AS INTEGER) AS hour,
                   COUNT(*) AS n
            FROM incidents WHERE {where}
            GROUP BY hour ORDER BY hour
            """,
            args,
        )
    ]
    hotspots = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT intersection, neighborhood, district, COUNT(*) AS n,
                   AVG(lat) AS lat, AVG(lon) AS lon
            FROM incidents
            WHERE {where} AND intersection IS NOT NULL
            GROUP BY intersection, neighborhood, district
            ORDER BY n DESC LIMIT 8
            """,
            args,
        )
    ]
    last = conn.execute(
        "SELECT MAX(ingested_at) AS ingested_at, MAX(received_datetime) AS latest FROM incidents"
    ).fetchone()
    districts = [
        row["district"]
        for row in conn.execute(
            "SELECT DISTINCT district FROM incidents WHERE district IS NOT NULL ORDER BY district"
        )
    ]
    return {
        "total": total,
        "open": open_n,
        "mapped": mapped,
        "by_category": by_cat,
        "by_neighborhood": by_hood,
        "by_hour": by_hour,
        "hotspots": hotspots,
        "districts": districts,
        "categories": category_meta(),
        "ingested_at": last["ingested_at"],
        "latest_incident": last["latest"],
        "window": window,
    }
