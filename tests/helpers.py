from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")


def pacific_iso(*, days: int = 0, hours: int = 0) -> str:
    dt = datetime.now(PACIFIC) - timedelta(days=days, hours=hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000")


def incident_row(**overrides) -> dict:
    row = {
        "cad_number": "1001",
        "received_datetime": pacific_iso(hours=1),
        "dispatch_datetime": pacific_iso(hours=1),
        "onscene_datetime": pacific_iso(hours=1),
        "close_datetime": None,
        "call_last_updated_at": pacific_iso(hours=1),
        "call_type": "909",
        "call_type_desc": "TRAFFIC STOP",
        "call_type_final": "909",
        "call_type_final_desc": "TRAFFIC STOP",
        "priority": "B",
        "agency": "Police",
        "disposition": None,
        "onview": 1,
        "sensitive": 0,
        "intersection": "MARKET ST \\ 6TH ST",
        "lat": 37.782,
        "lon": -122.41,
        "neighborhood": "South of Market",
        "district": "SOUTHERN",
        "supervisor_district": "6",
        "pd_incident_report": None,
        "category": "traffic",
        "routine": 0,
        "severity": 4,
        "status": "open",
        "source": "realtime",
        "ingested_at": "2026-09-02T18:00:00Z",
    }
    row.update(overrides)
    return row


def cad_payload(**overrides) -> dict:
    row = {
        "cad_number": "262450001",
        "received_datetime": "2026-09-02T10:00:00.000",
        "dispatch_datetime": "2026-09-02T10:01:00.000",
        "onscene_datetime": "2026-09-02T10:05:00.000",
        "close_datetime": "2026-09-02T10:20:00.000",
        "call_type_original": "909",
        "call_type_original_desc": "TRAFFIC STOP",
        "call_type_final": "909",
        "call_type_final_desc": "TRAFFIC STOP",
        "priority_final": "B",
        "agency": "Police",
        "onview_flag": "Y",
        "sensitive_call": False,
        "intersection_name": "MARKET ST \\ 6TH ST",
        "intersection_point": {
            "type": "Point",
            "coordinates": [-122.41, 37.782],
        },
        "analysis_neighborhood": "South of Market",
        "police_district": "SOUTHERN",
        "supervisor_district": "6",
    }
    row.update(overrides)
    return row
