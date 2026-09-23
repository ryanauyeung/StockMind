"""NYSE cash-session calendar helpers (lightweight, no market-calendars dep)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

_ET = ZoneInfo("America/New_York")

# Cash equity regular hours (ET). Session is complete only at/after the close.
_SESSION_CLOSE_HOUR = 16
_SESSION_CLOSE_MINUTE = 0


def _easter_sunday(year: int) -> pd.Timestamp:
    """Anonymous Gregorian algorithm → Easter Sunday (Western)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return pd.Timestamp(year=year, month=month, day=day)


def _observed_fixed(d: pd.Timestamp) -> pd.Timestamp:
    """NYSE Saturday→Friday / Sunday→Monday observance for fixed-date holidays."""
    wd = int(d.weekday())
    if wd == 5:  # Saturday
        return d - pd.Timedelta(days=1)
    if wd == 6:  # Sunday
        return d + pd.Timedelta(days=1)
    return d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> pd.Timestamp:
    """n-th weekday in month (Mon=0 … Sun=6)."""
    first = pd.Timestamp(year=year, month=month, day=1)
    offset = (weekday - int(first.weekday())) % 7
    return first + pd.Timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> pd.Timestamp:
    """Last weekday in month (Mon=0 … Sun=6)."""
    if month == 12:
        last = pd.Timestamp(year=year + 1, month=1, day=1) - pd.Timedelta(days=1)
    else:
        last = pd.Timestamp(year=year, month=month + 1, day=1) - pd.Timedelta(days=1)
    offset = (int(last.weekday()) - weekday) % 7
    return last - pd.Timedelta(days=offset)


def nyse_holidays_for_year(year: int) -> set[pd.Timestamp]:
    """Full-day NYSE cash equity holidays for ``year`` (normalized dates)."""
    holidays = {
        _observed_fixed(pd.Timestamp(year=year, month=1, day=1)),  # New Year
        _nth_weekday(year, 1, 0, 3),  # MLK Day
        _nth_weekday(year, 2, 0, 3),  # Presidents Day
        _easter_sunday(year) - pd.Timedelta(days=2),  # Good Friday
        _last_weekday(year, 5, 0),  # Memorial Day
        _observed_fixed(pd.Timestamp(year=year, month=6, day=19)),  # Juneteenth
        _observed_fixed(pd.Timestamp(year=year, month=7, day=4)),  # Independence
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed_fixed(pd.Timestamp(year=year, month=12, day=25)),  # Christmas
    }
    # New Year observed on Dec 31 of previous year when Jan 1 is Saturday
    nye_obs = _observed_fixed(pd.Timestamp(year=year + 1, month=1, day=1))
    if nye_obs.year == year:
        holidays.add(nye_obs)
    return {h.normalize() for h in holidays}


def is_nyse_trading_day(day: pd.Timestamp) -> bool:
    """True if ``day`` (date) is a weekday that is not an NYSE full-day holiday."""
    d = pd.Timestamp(day).normalize()
    if int(d.weekday()) >= 5:
        return False
    return d not in nyse_holidays_for_year(int(d.year))


def last_complete_nyse_session(now: datetime | pd.Timestamp | None = None) -> pd.Timestamp:
    """Return the normalized date of the last *complete* NYSE cash session.

    ``now`` is interpreted in America/New_York (naive values are treated as ET).

    Rules
    -----
    - A trading day's cash session is complete only at/after 16:00 ET.
    - If ``now`` falls on a trading day before the close (including pre-open and
      09:30–16:00), return the **previous** session.
    - If ``now`` is after the close on a trading day, return **that** day.
    - On weekends / full-day holidays, walk backward to the prior session.

    Holidays cover the usual US equity set (New Year, MLK, Presidents, Good
    Friday via Easter approximation, Memorial, Juneteenth, Independence, Labor,
    Thanksgiving, Christmas) with Saturday/Sunday observance — no
    ``pandas_market_calendars`` dependency.
    """
    if now is None:
        et = datetime.now(_ET)
    else:
        ts = pd.Timestamp(now)
        if ts.tzinfo is None:
            et = ts.to_pydatetime().replace(tzinfo=_ET)
        else:
            et = ts.tz_convert(_ET).to_pydatetime()

    candidate = pd.Timestamp(year=et.year, month=et.month, day=et.day)
    # Session not yet complete today → start walk from yesterday.
    after_close = (et.hour, et.minute) >= (_SESSION_CLOSE_HOUR, _SESSION_CLOSE_MINUTE)
    if not (is_nyse_trading_day(candidate) and after_close):
        candidate = candidate - pd.Timedelta(days=1)

    for _ in range(15):  # enough to clear long holiday weekends
        if is_nyse_trading_day(candidate):
            return candidate.normalize()
        candidate = candidate - pd.Timedelta(days=1)

    # Should be unreachable for a sane holiday calendar.
    return candidate.normalize()
