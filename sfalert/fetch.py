from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from .categories import categorize

REALTIME_URL = "https://data.sfgov.org/resource/gnap-fj3t.json"
CLOSED_URL = "https://data.sfgov.org/resource/2zdj-bwza.json"
PAGE_SIZE = 50000
USER_AGENT = "sfalert/0.1 (local CAD research; github.com/local)"


def _headers() -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    token = os.environ.get("SFALERT_APP_TOKEN") or os.environ.get("SODA_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    return headers


def soda_get(url: str, params: dict[str, str], retries: int = 4) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(params)
    full = f"{url}?{query}"
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(full, headers=_headers())
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if isinstance(payload, dict) and payload.get("error"):
                raise RuntimeError(payload.get("message") or "Socrata error")
            if not isinstance(payload, list):
                raise RuntimeError(f"Unexpected SODA payload: {type(payload)}")
            return payload
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            last_err = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed fetching {url}: {last_err}") from last_err


def _parse_point(row: dict[str, Any]) -> tuple[float | None, float | None]:
    point = row.get("intersection_point")
    if isinstance(point, dict):
        coords = point.get("coordinates") or []
        if len(coords) >= 2:
            lon, lat = float(coords[0]), float(coords[1])
            if -123.2 <= lon <= -122.2 and 37.6 <= lat <= 37.9:
                return lat, lon
    if isinstance(point, str) and point.upper().startswith("POINT"):
        inner = point.replace("POINT", "").replace("(", "").replace(")", "").strip()
        parts = inner.split()
        if len(parts) == 2:
            lon, lat = float(parts[0]), float(parts[1])
            return lat, lon
    return None, None


def _truthy(value: Any) -> int:
    if value is True or value == 1:
        return 1
    if isinstance(value, str) and value.strip().upper() in {"TRUE", "Y", "YES", "1"}:
        return 1
    return 0


def normalize(row: dict[str, Any], source: str, ingested_at: str) -> dict[str, Any]:
    desc = row.get("call_type_final_desc") or row.get("call_type_original_desc") or ""
    category, routine, severity = categorize(desc)
    lat, lon = _parse_point(row)
    close_dt = row.get("close_datetime") or ""
    status = "closed" if close_dt else "open"
    cad = str(row.get("cad_number") or "").strip()
    return {
        "cad_number": cad,
        "received_datetime": row.get("received_datetime") or None,
        "dispatch_datetime": row.get("dispatch_datetime") or None,
        "onscene_datetime": row.get("onscene_datetime") or None,
        "close_datetime": close_dt or None,
        "call_last_updated_at": row.get("call_last_updated_at") or row.get("data_updated_at"),
        "call_type": row.get("call_type_original"),
        "call_type_desc": row.get("call_type_original_desc"),
        "call_type_final": row.get("call_type_final"),
        "call_type_final_desc": desc or None,
        "priority": row.get("priority_final") or row.get("priority_original"),
        "agency": row.get("agency"),
        "disposition": row.get("disposition"),
        "onview": _truthy(row.get("onview_flag")),
        "sensitive": _truthy(row.get("sensitive_call")),
        "intersection": row.get("intersection_name"),
        "lat": lat,
        "lon": lon,
        "neighborhood": row.get("analysis_neighborhood"),
        "district": row.get("police_district"),
        "supervisor_district": row.get("supervisor_district"),
        "pd_incident_report": row.get("pd_incident_report"),
        "category": category,
        "routine": 1 if routine else 0,
        "severity": severity,
        "status": status,
        "source": source,
        "ingested_at": ingested_at,
    }


def iso_days_ago(days: int) -> str:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    # CAD timestamps are naive local (Pacific) on DataSF; a UTC day window
    # is still a fine backfill bound.
    return start.strftime("%Y-%m-%dT00:00:00")


def iter_closed(days: int) -> Iterator[list[dict[str, Any]]]:
    start = iso_days_ago(days)
    offset = 0
    while True:
        batch = soda_get(
            CLOSED_URL,
            {
                "$where": f"received_datetime >= '{start}'",
                "$order": "received_datetime",
                "$limit": str(PAGE_SIZE),
                "$offset": str(offset),
            },
        )
        if not batch:
            break
        yield batch
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE


def fetch_realtime() -> list[dict[str, Any]]:
    offset = 0
    rows: list[dict[str, Any]] = []
    while True:
        batch = soda_get(
            REALTIME_URL,
            {
                "$order": "received_datetime DESC",
                "$limit": "50000",
                "$offset": str(offset),
            },
        )
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 50000:
            break
        offset += 50000
    return rows
