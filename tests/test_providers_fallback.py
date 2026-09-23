"""CombinedProvider retry + incomplete Close handling + NYSE coverage bar."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from stockmind.data.nyse_session import last_complete_nyse_session
from stockmind.data.providers import CombinedProvider, _normalize_yf_frame
from stockmind.data.store import equity_session_coverage

_ET = ZoneInfo("America/New_York")


def _bars(ticker: str, dates: list[str], source: str = "yfinance") -> pd.DataFrame:
    rows = []
    for d in dates:
        rows.append(
            {
                "date": pd.Timestamp(d),
                "ticker": ticker,
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "adj_close": 1.0,
                "volume": 100,
                "source": source,
            }
        )
    return pd.DataFrame(rows)


@dataclass
class _FakeYahooSparsePanel:
    """Batch has sparse newest day (^VIX only); equities stop at last complete session."""

    singles: list = field(default_factory=list)
    equity_dates: list[str] = field(default_factory=lambda: ["2026-09-18", "2026-09-21"])
    vix_dates: list[str] = field(
        default_factory=lambda: ["2026-09-18", "2026-09-21", "2026-09-22"]
    )
    # Single-ticker retry (should not be needed when equity already hits NYSE target)
    retry_dates: list[str] | None = None

    def download(self, tickers, start, end=None):
        tickers = list(tickers)
        if len(tickers) == 1:
            t = tickers[0]
            self.singles.append(t)
            if t == "^VIX":
                return _bars("^VIX", self.vix_dates)
            dates = self.retry_dates if self.retry_dates is not None else self.equity_dates
            return _bars(t, dates)
        frames = [_bars("^VIX", self.vix_dates)]
        for t in tickers:
            if t == "^VIX":
                continue
            frames.append(_bars(t, self.equity_dates))
        return pd.concat(frames, ignore_index=True)


@dataclass
class _FakeStooq:
    called_with: list | None = None

    def download(self, tickers, start, end=None):
        self.called_with = list(tickers)
        return pd.DataFrame(
            columns=["date", "ticker", "open", "high", "low", "close", "adj_close", "volume", "source"]
        )


def test_nyse_coverage_skips_stooq_when_equities_have_last_complete(monkeypatch):
    """Sparse Yahoo panel_max (^VIX-only newer day) must not force Stooq for equities.

    Equities already include the last complete NYSE session; coverage uses that
    bar, not panel_max.
    """
    target = pd.Timestamp("2026-09-21")
    monkeypatch.setattr(
        "stockmind.data.providers.last_complete_nyse_session",
        lambda now=None: target,
    )
    yahoo = _FakeYahooSparsePanel()
    stooq = _FakeStooq()
    combined = CombinedProvider(yahoo=yahoo, stooq=stooq)  # type: ignore[arg-type]
    out = combined.download(["AAPL", "MSFT", "^VIX"], start="2026-09-10", end="2026-09-23")
    assert stooq.called_with is None
    assert yahoo.singles == []
    for t in ("AAPL", "MSFT"):
        tmax = pd.to_datetime(out.loc[out["ticker"] == t, "date"]).dt.normalize().max()
        assert tmax >= target


def test_sparse_panel_max_only_on_one_ticker_missing_count_zero(monkeypatch):
    """Only ^VIX has the sparse newest day → missing count 0, Stooq not invoked."""
    target = pd.Timestamp("2026-09-21")
    monkeypatch.setattr(
        "stockmind.data.providers.last_complete_nyse_session",
        lambda now=None: target,
    )
    yahoo = _FakeYahooSparsePanel()
    stooq = _FakeStooq()
    combined = CombinedProvider(yahoo=yahoo, stooq=stooq)  # type: ignore[arg-type]
    out = combined.download(["AAPL", "^VIX"], start="2026-09-10", end="2026-09-23")
    assert yahoo.singles == []
    assert stooq.called_with is None
    assert set(out["ticker"]) >= {"AAPL", "^VIX"}
    # panel_max would be 2026-09-22 from VIX alone; AAPL still covered via NYSE bar
    aapl_max = pd.to_datetime(out.loc[out["ticker"] == "AAPL", "date"]).dt.normalize().max()
    assert aapl_max == target
    vix_max = pd.to_datetime(out.loc[out["ticker"] == "^VIX", "date"]).dt.normalize().max()
    assert vix_max == pd.Timestamp("2026-09-22")


def test_single_yahoo_retry_when_behind_nyse_target(monkeypatch):
    """Ticker behind NYSE target still gets single-ticker Yahoo retry (not panel_max)."""
    target = pd.Timestamp("2026-09-21")
    monkeypatch.setattr(
        "stockmind.data.providers.last_complete_nyse_session",
        lambda now=None: target,
    )

    @dataclass
    class _YahooBehind:
        singles: list = field(default_factory=list)

        def download(self, tickers, start, end=None):
            tickers = list(tickers)
            if tickers == ["AAPL"]:
                self.singles.append("AAPL")
                return _bars("AAPL", ["2026-09-18", "2026-09-21"])
            return pd.concat(
                [
                    _bars("^VIX", ["2026-09-18", "2026-09-21"]),
                    _bars("AAPL", ["2026-09-18"]),
                ],
                ignore_index=True,
            )

    yahoo = _YahooBehind()
    stooq = _FakeStooq()
    combined = CombinedProvider(yahoo=yahoo, stooq=stooq)  # type: ignore[arg-type]
    out = combined.download(["AAPL", "^VIX"], start="2026-09-10", end="2026-09-23")
    assert yahoo.singles == ["AAPL"]
    aapl = out[out["ticker"] == "AAPL"]
    assert pd.Timestamp("2026-09-21") in set(pd.to_datetime(aapl["date"]).dt.normalize())
    assert stooq.called_with is None


def test_last_complete_nyse_session_mid_session_returns_prior():
    # Wednesday 2026-09-23 12:00 ET → session still open → prior day Tue 2026-09-22
    now = datetime(2026, 9, 23, 12, 0, tzinfo=_ET)
    assert last_complete_nyse_session(now) == pd.Timestamp("2026-09-22")


def test_last_complete_nyse_session_after_close_returns_that_day():
    # Wednesday 2026-09-23 16:00 ET → complete → that day
    now = datetime(2026, 9, 23, 16, 0, tzinfo=_ET)
    assert last_complete_nyse_session(now) == pd.Timestamp("2026-09-23")


def test_last_complete_nyse_session_saturday_returns_friday():
    # Saturday 2026-09-19 → Friday 2026-09-18 was a session
    now = datetime(2026, 9, 19, 10, 0, tzinfo=_ET)
    assert last_complete_nyse_session(now) == pd.Timestamp("2026-09-18")


def test_last_complete_nyse_session_preopen_returns_prior():
    # Trading day before open still incomplete → prior session
    now = datetime(2026, 9, 23, 8, 0, tzinfo=_ET)
    assert last_complete_nyse_session(now) == pd.Timestamp("2026-09-22")


def test_normalize_drops_row_when_close_and_adj_nan():
    part = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-09-14")],
            "open": [10.0],
            "high": [12.0],
            "low": [9.0],
            "close": [float("nan")],
            "adj_close": [float("nan")],
            "volume": [1000],
        }
    )
    out = _normalize_yf_frame(part, "AAPL")
    assert out.empty


def test_normalize_uses_adj_close_when_close_nan():
    part = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-09-14")],
            "open": [10.0],
            "high": [12.0],
            "low": [9.0],
            "close": [float("nan")],
            "adj_close": [11.0],
            "volume": [1000],
        }
    )
    out = _normalize_yf_frame(part, "AAPL")
    assert len(out) == 1
    assert float(out.iloc[0]["close"]) == 11.0


def test_equity_session_coverage_incomplete():
    # Only one real S&P name on the day → well under 90% of the Wikipedia list.
    ohlcv = pd.concat(
        [
            _bars("AAPL", ["2026-09-14"]),
            _bars("^VIX", ["2026-09-14"]),
        ],
        ignore_index=True,
    )
    cov = equity_session_coverage(ohlcv, "2026-09-14")
    assert cov["n_have"] == 1
    assert cov["frac"] < 0.90
    assert cov["complete"] is False
