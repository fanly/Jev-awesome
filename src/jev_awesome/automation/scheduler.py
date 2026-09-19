from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

UTC_CRON = "17 0,6,12,18 * * *"
# UTC+8 wall clocks: 02:17, 08:17, 14:17, 20:17


@dataclass
class ScheduleWindow:
    name: str
    every: timedelta
    last_success: datetime | None = None

    def due(self, now: datetime) -> bool:
        if self.last_success is None:
            return True
        return now - self.last_success >= self.every


def cron_hours_utc() -> list[int]:
    return [0, 6, 12, 18]


def describe_schedule(tz_name: str = "Asia/Shanghai") -> list[str]:
    tz = ZoneInfo(tz_name)
    lines = []
    for h in cron_hours_utc():
        utc_dt = datetime(2026, 1, 1, h, 17, tzinfo=UTC)
        local = utc_dt.astimezone(tz)
        lines.append(f"UTC {h:02d}:17 → {tz_name} {local.strftime('%H:%M')} (cron `{UTC_CRON}`)")
    return lines


def should_run_after_delay(
    scheduled_utc: datetime, actual_utc: datetime, window: timedelta = timedelta(hours=6)
) -> bool:
    """Delayed Actions runs still eligible within the slot window."""
    return scheduled_utc <= actual_utc < scheduled_utc + window
