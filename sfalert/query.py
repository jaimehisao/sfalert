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


def _fts_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='incidents_fts'"
    ).fetchone()
    return row is not None


def _like_clause(q: str) -> tuple[str, list[Any]]:
    like = f"%{_escape_like(q)}%"
    clauses = [f"{col} LIKE ? ESCAPE '\\'" for col in _LIKE_COLUMNS]
    return " AND (" + " OR ".join(clauses) + ")", [like] * len(_LIKE_COLUMNS)


def _search_clause(
    conn: sqlite3.Connection, q: str | None
) -> tuple[str, list[Any]]:
    """Build the search predicate shared by feed, heatmap, and stats.

    Trigram FTS (`incidents_fts MATCH '"q"'`) gives LIKE '%q%' semantics
    without a full scan; short queries (<3 chars), missing FTS tables,
    and MATCH errors fall back to the parameterized LIKE.
    """
    if not q:
        return "", []
    text = q.strip()
    if len(text) >= 3:
        try:
            if _fts_table_exists(conn):
                phrase = '"' + text.replace('"', '""') + '"'
                return (
                    " AND cad_number IN ("
                    "SELECT cad_number FROM incidents_fts "
                    "WHERE incidents_fts MATCH ?)",
                    [phrase],
                )
        except Exception:
            pass
    return _like_clause(q)


def _run_with_search_fallback(
    conn: sqlite3.Connection,
    sql: str,
    args: list[Any],
    q: str | None,
    search_where: str,
    search_args: list[Any],
    where: str,
) -> list[sqlite3.Row]:
    """Execute a search query, falling back to LIKE if FTS MATCH fails."""
    try:
        return list(conn.execute(sql, args).fetchall())
    except sqlite3.OperationalError:
        if "MATCH" not in search_where:
            raise
        like_where, like_args = _like_clause(q or "")
        fallback_sql = sql.replace(search_where, like_where)
        # Rebuild args: base filters + LIKE args (+ LIMIT tail preserved
        # by replacing only the search fragment).
        base_len = len(args) - len(search_args)
        # Preserve any trailing LIMIT arg (list_incidents appends it).
        trailing: list[Any] = []
        if "LIMIT ?" in sql:
            trailing = args[-1:]
            base_len -= 1
        fallback_args = args[:base_len] + like_args + trailing
        return list(conn.execute(fallback_sql, fallback_args).fetchall())


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
    search_where, search_args = _search_clause(conn, q)
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
    rows = _run_with_search_fallback(
        conn, sql, [*args, *search_args, limit], q, search_where, search_args, where
    )
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
    search_where, search_args = _search_clause(conn, q)
    sql = f"""
        SELECT ROUND(lat, 4) AS lat, ROUND(lon, 4) AS lon,
               COUNT(*) AS n, SUM(severity) AS weight
        FROM incidents
        WHERE {where}{search_where} AND lat IS NOT NULL AND lon IS NOT NULL
        GROUP BY ROUND(lat, 4), ROUND(lon, 4)
    """
    rows = _run_with_search_fallback(
        conn, sql, [*args, *search_args], q, search_where, search_args, where
    )
    max_w = max((row["weight"] or 0) for row in rows) if rows else 1
    points = []
    for row in rows:
        intensity = (row["weight"] or 0) / max_w if max_w else 0
        points.append([row["lat"], row["lon"], round(max(intensity, 0.12), 3)])
    return points


def bundle(
    conn: sqlite3.Connection,
    window: str = "24h",
    category: str | None = None,
    district: str | None = None,
    hide_routine: bool = True,
    status: str | None = None,
    limit: int = 200,
    q: str | None = None,
) -> dict[str, Any]:
    """Feed + heatmap + stats in one connection.

    The UI previously issued 3 parallel requests per poll (3 connects,
    3 round trips). Status only scopes the feed; heat and stats stay
    window-wide so pins/heat/stats agree with the legacy endpoints.
    """
    return {
        "incidents": list_incidents(
            conn,
            window=window,
            category=category,
            district=district,
            hide_routine=hide_routine,
            status=status,
            limit=limit,
            q=q,
        ),
        "heat": heatmap_points(
            conn,
            window=window,
            category=category,
            district=district,
            hide_routine=hide_routine,
            q=q,
        ),
        "stats": stats(
            conn,
            window=window,
            category=category,
            district=district,
            hide_routine=hide_routine,
            q=q,
        ),
    }


def stats(
    conn: sqlite3.Connection,
    window: str = "24h",
    category: str | None = None,
    district: str | None = None,
    hide_routine: bool = True,
    q: str | None = None,
) -> dict[str, Any]:
    where, args = _filters(window, category, district, hide_routine, None)
    search_where, search_args = _search_clause(conn, q)
    # Every aggregate below shares this WHERE, so a search scopes the
    # counts, chips, hour bars, and hotspots the same way it scopes the feed.
    base_where, base_args = where, list(args)
    where += search_where
    args = [*args, *search_args]
    try:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM incidents WHERE {where}", args
        ).fetchone()["n"]
    except sqlite3.OperationalError:
        if "MATCH" not in search_where:
            raise
        like_where, like_args = _like_clause(q or "")
        where = base_where + like_where
        args = [*base_args, *like_args]
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
