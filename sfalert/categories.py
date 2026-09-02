"""Map SF CAD call-type strings onto heatmap / feed categories."""

from __future__ import annotations

CATEGORIES: dict[str, dict[str, object]] = {
    "violence": {"label": "Violence", "color": "#ff4d4d", "weight": 5},
    "theft": {"label": "Theft", "color": "#ff8a3d", "weight": 4},
    "welfare": {"label": "Welfare", "color": "#c084fc", "weight": 3},
    "traffic": {"label": "Traffic", "color": "#60a5fa", "weight": 4},
    "quality": {"label": "Quality of life", "color": "#fbbf24", "weight": 2},
    "suspicious": {"label": "Suspicious", "color": "#2dd4bf", "weight": 2},
    "alarm": {"label": "Alarm", "color": "#94a3b8", "weight": 2},
    "police": {"label": "Police action", "color": "#818cf8", "weight": 2},
    "other": {"label": "Other", "color": "#64748b", "weight": 1},
}

# Order matters: first match wins. Keep "WEAPON" out — it hits "FIGHT NO WEAPON".
_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "violence",
        (
            "ASSAULT",
            "BATTERY",
            "FIGHT",
            "ROBBERY",
            "PERSON W/GUN",
            "PERSON W/KNIFE",
            "STABBING",
            "SHOOTING",
            "SHOTS",
            "HOMICIDE",
            "CARJACK",
            "RAPE",
            "SEXUAL",
            "GUNSHOT",
            "BRANDISH",
            "STRONG ARM",
            "KNIFE",
            "STAB",
            "THREATS",
            "DOMESTIC",
            " DV",
        ),
    ),
    (
        "theft",
        (
            "THEFT",
            "BURGLARY",
            "STOLEN",
            "AUTO BOOST",
            "SHOPLIFT",
            "STOLEN VEHICLE",
            "FRAUD",
            "FORGERY",
        ),
    ),
    (
        "welfare",
        (
            "WELL BEING",
            "WELFARE",
            "SUICIDE",
            "MENTALLY",
            "MISSING",
            "AIDED",
            "OVERDOSE",
            "INTOXICATED",
            "SICK",
            "INJURED PERSON",
            "PERSON DOWN",
        ),
    ),
    (
        "alarm",
        ("ALARM",),
    ),
    (
        "traffic",
        (
            "TRAF ",
            "TRAFFIC",
            "VEH ACCIDENT",
            "INJURY VEH",
            "HIT & RUN",
            "HIT AND RUN",
            "TOW",
            "COLLISION",
        ),
    ),
    (
        "quality",
        (
            "NOISE",
            "TRESPASS",
            "HOMELESS",
            "SIT/LIE",
            "INDECENT",
            "DRUNK",
            "LOITER",
            "PANHANDL",
            "URINAT",
            "DISTURB",
        ),
    ),
    (
        "suspicious",
        ("SUSPICIOUS", "COMPLAINT UNKN"),
    ),
    (
        "police",
        (
            "ARREST",
            "WANTED",
            "PRISONER",
            "SEARCH WARRANT",
            "BACKUP",
            "PURSUIT",
        ),
    ),
]

# Radio/admin noise only. Traffic stops and cites stay in the heatmap —
# they cluster tightly and are one of the better CAD hotspot signals.
_ROUTINE = (
    "PASSING CALL",
    "MEET W/",
    "TOW TRUCK",
    "PRISONER TRANSPORT",
    "MUNI INSPECT",
    "PARKING",
    "INFO",
)

_HOTSPOT_TRAFFIC = (
    "TRAFFIC STOP",
    "TRAF VIOLATION CITE",
    "TRAF VIOLATION TOW",
)


def categorize(call_type_desc: str | None) -> tuple[str, bool, int]:
    """Return (category, is_routine, heatmap_weight)."""
    text = (call_type_desc or "").upper()
    if not text:
        return "other", False, 1
    if any(token in text for token in _HOTSPOT_TRAFFIC):
        return "traffic", False, int(CATEGORIES["traffic"]["weight"])
    routine = any(token in text for token in _ROUTINE)
    for category, needles in _RULES:
        if any(needle in text for needle in needles):
            weight = int(CATEGORIES[category]["weight"])
            if routine:
                weight = 1
            return category, routine, weight
    if routine:
        return "other", True, 1
    return "other", False, 1


def category_meta() -> list[dict[str, object]]:
    rows = []
    for key, meta in CATEGORIES.items():
        rows.append({"id": key, **meta})
    return rows
