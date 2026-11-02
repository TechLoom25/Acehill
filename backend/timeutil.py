"""Shop-local time handling. The database stores UTC; "today" and "this week" are decided in the shop's time zone."""
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from config import SHOP_TIMEZONE


def shop_tz() -> ZoneInfo:
    return ZoneInfo(SHOP_TIMEZONE)


def as_utc(value: datetime) -> datetime:
    """Treat a naive datetime as UTC (how every timestamp is stored) instead of as the server's local time."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def period_bounds(period: str, now: datetime, tz: Optional[ZoneInfo] = None) -> tuple[datetime, datetime]:
    """Return [start, end) as timezone-aware UTC datetimes. Weeks run Monday to Sunday in shop time."""
    tz = tz or shop_tz()
    today = datetime.combine(as_utc(now).astimezone(tz).date(), time.min, tzinfo=tz)
    if period == "today":
        start, end = today, today + timedelta(days=1)
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=7)
    elif period == "last_week":
        end = today - timedelta(days=today.weekday())
        start = end - timedelta(days=7)
    else:
        first = today.replace(day=1)
        if period == "month":
            start, end = first, (first + timedelta(days=32)).replace(day=1)
        else:  # last_month
            end = first
            start = (first - timedelta(days=1)).replace(day=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def week_start(now: datetime) -> datetime:
    """Monday 00:00 in shop time, as UTC. The dashboard and the finance page now agree on what "this week" is."""
    return period_bounds("week", now)[0]
