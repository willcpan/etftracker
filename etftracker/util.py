from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

_DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "mdy"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2})\b"), "mdy2"),
    (re.compile(r"(?<![\d-])(\d{1,2})-(\d{1,2})-(\d{4})(?!\d)"), "mdy"),
    (re.compile(r"(?<![\d-])(\d{1,2})_(\d{1,2})_(\d{4})(?!\d)"), "mdy"),
    (re.compile(r"\b(\d{4})(\d{2})(\d{2})\b"), "ymd_compact"),
    (
        re.compile(
            r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\b",
            re.IGNORECASE,
        ),
        "mon_d_y",
    ),
    (
        re.compile(
            r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{4})\b",
            re.IGNORECASE,
        ),
        "d_mon_y",
    ),
]
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_date(text: str | None) -> date | None:
    """Find the first plausible calendar date in free text. Returns None if nothing matches."""
    if not text:
        return None
    text = str(text)
    for pat, kind in _DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        try:
            if kind == "ymd":
                d = date(int(m[1]), int(m[2]), int(m[3]))
            elif kind == "mdy":
                d = date(int(m[3]), int(m[1]), int(m[2]))
            elif kind == "mdy2":
                d = date(2000 + int(m[3]), int(m[1]), int(m[2]))
            elif kind == "ymd_compact":
                d = date(int(m[1]), int(m[2]), int(m[3]))
            elif kind == "mon_d_y":
                d = date(int(m[3]), _MONTHS[m[1][:3].lower()], int(m[2]))
            else:
                d = date(int(m[3]), _MONTHS[m[2][:3].lower()], int(m[1]))
        except ValueError:
            continue
        if 2000 <= d.year <= 2100:
            return d
    return None


def today_et() -> date:
    return datetime.now(ET).date()


def now_utc_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def previous_business_day(d: date) -> date:
    d = d - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


_NUM_CLEAN = re.compile(r"[,$%\s]")


def to_float(value) -> float | None:
    """Parse numbers as they appear in fund files: '1,234.5', '$12.30', '(45)', '3.2%', '-'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s in {"", "-", "--", "—", "N/A", "n/a", "NA", "null", "None"}:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = _NUM_CLEAN.sub("", s.strip("()"))
    if s.startswith("-"):
        neg, s = True, s[1:]
    try:
        f = float(s)
    except ValueError:
        return None
    return -f if neg else f


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
