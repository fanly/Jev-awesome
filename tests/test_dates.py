from __future__ import annotations

from jev_awesome.dates import parse_flexible_date


def test_t04_missing_date():
    d = parse_flexible_date(None)
    assert d.value is None and d.precision == "unknown"


def test_t04_year_only():
    d = parse_flexible_date("2024")
    assert d.precision == "year"
    assert d.value is not None


def test_t04_invalid_rss_date_not_today():
    d = parse_flexible_date("not-a-date")
    assert d.value is None
    assert d.precision == "unknown"
    assert d.raw == "not-a-date"


def test_t04_day_precision_no_fake_time():
    d = parse_flexible_date("2024-05-01")
    assert d.precision == "day"
    from datetime import date, datetime

    assert isinstance(d.value, date) and not isinstance(d.value, datetime)
