from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

from dateutil import parser as date_parser

from jev_awesome.models import FlexibleDate


def parse_flexible_date(
    raw: Any, *, source: str | None = None, now: datetime | None = None
) -> FlexibleDate:
    """Parse dates without inventing missing precision or using today as publish date."""
    _ = now  # explicit: never use now as published_at
    if raw is None or raw == "":
        return FlexibleDate(value=None, precision="unknown", raw=None, source=source)

    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            raw = raw.replace(tzinfo=UTC)
        return FlexibleDate(value=raw, precision="datetime", raw=str(raw), source=source)

    if isinstance(raw, date) and not isinstance(raw, datetime):
        return FlexibleDate(value=raw, precision="day", raw=str(raw), source=source)

    text = str(raw).strip()
    if not text or text.lower() in {"none", "null", "n/a", "unknown"}:
        return FlexibleDate(value=None, precision="unknown", raw=text, source=source)

    # Year only
    if re.fullmatch(r"\d{4}", text):
        try:
            return FlexibleDate(
                value=date(int(text), 1, 1),
                precision="year",
                raw=text,
                source=source,
            )
        except ValueError:
            return FlexibleDate(value=None, precision="unknown", raw=text, source=source)

    # Year-month
    if re.fullmatch(r"\d{4}-\d{2}", text):
        y, m = text.split("-")
        try:
            return FlexibleDate(
                value=date(int(y), int(m), 1),
                precision="month",
                raw=text,
                source=source,
            )
        except ValueError:
            return FlexibleDate(value=None, precision="unknown", raw=text, source=source)

    try:
        dt = date_parser.parse(text, default=datetime(1900, 1, 1))
    except (ValueError, OverflowError, TypeError):
        return FlexibleDate(value=None, precision="unknown", raw=text, source=source)

    # Detect if time was present
    has_time = bool(re.search(r"\d{1,2}:\d{2}", text)) or "T" in text
    if has_time:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return FlexibleDate(value=dt, precision="datetime", raw=text, source=source)

    return FlexibleDate(
        value=dt.date() if isinstance(dt, datetime) else dt,
        precision="day",
        raw=text,
        source=source,
    )


def utc_now() -> datetime:
    return datetime.now(UTC)
