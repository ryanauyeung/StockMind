"""Historical card snapshots under data/artifacts/history/ (deploy-friendly; no git at runtime)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from stockmind.config import ARTIFACT_DIR

HISTORY_DIR = ARTIFACT_DIR / "history"
HISTORY_INDEX = HISTORY_DIR / "index.json"

_FAMILY_FILE = {
    "shared": "cards_shared.json",
    "sector": "cards_sector.json",
    "stock": "cards_stock.json",
}


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_available_asofs() -> list[str]:
    """Newest-first asof strings that have at least one family snapshot."""
    idx = _read_json(HISTORY_INDEX) or {}
    asofs = [e.get("asof") for e in (idx.get("asofs") or []) if e.get("asof")]
    if asofs:
        return [a for a in asofs if a]
    # Fallback: scan directories
    if not HISTORY_DIR.exists():
        return []
    days = sorted(
        (p.name for p in HISTORY_DIR.iterdir() if p.is_dir() and p.name[:4].isdigit()),
        reverse=True,
    )
    return days


def load_history_cards(family: str, asof: str) -> dict | None:
    """Load cards_{family}.json for a historical asof, or None if missing."""
    fname = _FAMILY_FILE.get(family)
    if not fname or not asof:
        return None
    path = HISTORY_DIR / asof / fname
    payload = _read_json(path)
    if payload is None:
        return None
    # Tag so UI can tell live vs history
    payload = dict(payload)
    payload["_history"] = True
    payload["_history_path"] = str(path.relative_to(ARTIFACT_DIR.parent)) if ARTIFACT_DIR.parent in path.parents else str(path)
    return payload


def family_has_asof(family: str, asof: str) -> bool:
    """True if history/{asof}/cards_{family}.json exists."""
    fname = _FAMILY_FILE.get(family)
    if not fname or not asof:
        return False
    return (HISTORY_DIR / str(asof) / fname).is_file()


def nearby_asofs(asof: str, options: list[str], k: int = 2) -> dict[str, list[str]]:
    """Nearby dates from options sorted newest-first: newer (before idx) / older (after)."""
    opts = [str(o) for o in (options or []) if o]
    target = str(asof) if asof else ""
    if not opts or not target:
        return {"newer": [], "older": []}
    try:
        idx = opts.index(target)
    except ValueError:
        newer_all = [o for o in opts if o > target]
        older_all = [o for o in opts if o < target]
        # closest first
        return {"newer": list(reversed(newer_all))[:k], "older": older_all[:k]}
    newer = opts[max(0, idx - k) : idx]
    newer.reverse()  # closest newer first
    older = opts[idx + 1 : idx + 1 + k]
    return {"newer": newer, "older": older}


def snapshot_cards_to_history(cards_by_family: dict[str, dict]) -> Path | None:
    """Persist today's family payloads into history/ and refresh index.json.

    Called after nightly / pipeline writes live cards. Safe no-op if empty.
    """
    if not cards_by_family:
        return None
    # Prefer shared asof as canonical
    asof = None
    for fam in ("shared", "sector", "stock"):
        payload = cards_by_family.get(fam) or {}
        asof = payload.get("asof") or asof
    if not asof:
        return None

    day_dir = HISTORY_DIR / str(asof)
    day_dir.mkdir(parents=True, exist_ok=True)
    entry_families: dict[str, Any] = {}
    for fam, fname in _FAMILY_FILE.items():
        payload = cards_by_family.get(fam)
        if not payload:
            continue
        (day_dir / fname).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        entry_families[fam] = {
            "file": f"history/{asof}/{fname}",
            "n_cards": payload.get("n_cards"),
            "n_long": payload.get("n_long"),
            "n_short": payload.get("n_short"),
            "n_flat": payload.get("n_flat"),
        }

    idx = _read_json(HISTORY_INDEX) or {"version": 1, "source": "nightly snapshot", "asofs": []}
    entries = [e for e in (idx.get("asofs") or []) if e.get("asof") != asof]
    new_entry = {
        "asof": asof,
        "generated_at_utc": (cards_by_family.get("shared") or {}).get("generated_at_utc"),
        "families": entry_families,
    }
    entries.insert(0, new_entry)
    idx["version"] = 1
    idx["asofs"] = entries
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return day_dir


def next_session_after(asof: str, ticker: str) -> pd.Timestamp | None:
    """Next regular session date after asof for ticker (via Yahoo), or None."""
    try:
        import yfinance as yf
    except ImportError:
        return None
    start = pd.Timestamp(asof)
    end = start + timedelta(days=12)
    try:
        df = yf.download(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=False,
            threads=False,
        )
    except Exception:
        return None
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    date_col = "Date" if "Date" in df.columns else df.columns[0]
    dates = pd.to_datetime(df[date_col]).dt.tz_localize(None).dt.normalize()
    after = dates[dates > start.normalize()]
    if after.empty:
        return None
    return pd.Timestamp(after.iloc[0])


def fetch_session_ohlc(ticker: str, session: str) -> dict[str, float] | None:
    """OHLC for one session date (Yahoo)."""
    try:
        import yfinance as yf
    except ImportError:
        return None
    day = pd.Timestamp(session)
    try:
        df = yf.download(
            ticker,
            start=day.strftime("%Y-%m-%d"),
            end=(day + timedelta(days=3)).strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=False,
            threads=False,
        )
    except Exception:
        return None
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    date_col = "Date" if "Date" in df.columns else df.columns[0]
    df["_d"] = pd.to_datetime(df[date_col]).dt.tz_localize(None).dt.normalize()
    row = df[df["_d"] == day.normalize()]
    if row.empty:
        return None
    r = row.iloc[0]
    try:
        return {
            "open": float(r["Open"]),
            "high": float(r["High"]),
            "low": float(r["Low"]),
            "close": float(r["Close"]),
            "session": day.strftime("%Y-%m-%d"),
        }
    except Exception:
        return None


def attach_actuals(card: dict, actual: dict[str, float] | None) -> dict:
    """Return a shallow copy of card with actuals, q50 errors, and compact marks."""
    out = dict(card)
    pred = card.get("pred") or {}

    def _mark_band(px, q10, q90) -> str:
        if px is None or q10 is None or q90 is None:
            return "—"
        lo, hi = float(q10), float(q90)
        if lo > hi:
            lo, hi = hi, lo
        v = float(px)
        return "✓" if lo <= v <= hi else "✗"

    def _entry_touch(action: str, entry_px, high, low) -> str:
        if action == "觀望" or entry_px is None:
            return "—"
        if action == "做多":
            if low is None:
                return "—"
            return "✓" if float(low) <= float(entry_px) else "✗"
        if action == "做空":
            if high is None:
                return "—"
            return "✓" if float(high) >= float(entry_px) else "✗"
        return "—"

    if not actual:
        out["actual"] = None
        out["actual_err"] = None
        out["actual_marks"] = {
            "high_in_band": "—",
            "low_in_band": "—",
            "entry_touch": "—",
        }
        return out

    out["actual"] = actual
    err: dict[str, float] = {}
    for tgt in ("high", "low", "close"):
        q50 = (pred.get(tgt) or {}).get("q50")
        px = actual.get(tgt)
        if q50 is not None and px is not None:
            err[tgt] = float(px) - float(q50)
            err[f"{tgt}_abs"] = abs(float(px) - float(q50))
    q50_close = (pred.get("close") or {}).get("q50")
    close_px = actual.get("close")
    if q50_close is not None and close_px is not None and float(q50_close) != 0:
        err["close_pct"] = (float(close_px) - float(q50_close)) / float(q50_close)
    out["actual_err"] = err

    high_pred = pred.get("high") or {}
    low_pred = pred.get("low") or {}
    out["actual_marks"] = {
        "high_in_band": _mark_band(actual.get("high"), high_pred.get("q10"), high_pred.get("q90")),
        "low_in_band": _mark_band(actual.get("low"), low_pred.get("q10"), low_pred.get("q90")),
        "entry_touch": _entry_touch(
            str(card.get("action") or ""),
            card.get("entry_px"),
            actual.get("high"),
            actual.get("low"),
        ),
    }
    return out
