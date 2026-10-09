"""Two-day prediction/result table helpers (昨日結果 + 今日預測)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

REASON_ZH = {
    "tp": "止盈出場",
    "sl": "止損出場",
    "close": "收市平倉",
}

TWO_DAY_COLUMNS = ("日", "方向", "入場", "止盈", "止損", "結果")


def resolve_pair_asofs(
    asofs: list[str], viewing: str | None = None
) -> tuple[str | None, str | None]:
    """Return (prev_asof, today_asof).

    today = viewing if present in asofs, else newest (asofs[0]).
    prev = next older entry in newest-first asofs list.
    """
    opts = [str(a) for a in (asofs or []) if a]
    if not opts:
        return None, None
    today = str(viewing) if viewing and str(viewing) in opts else opts[0]
    try:
        idx = opts.index(today)
    except ValueError:
        return None, today
    prev = opts[idx + 1] if idx + 1 < len(opts) else None
    return prev, today


def session_by_asof_from_ledger(ledger: dict | None) -> dict[str, str]:
    """Map asof -> session from ledger days."""
    out: dict[str, str] = {}
    for day in (ledger or {}).get("days") or []:
        a = day.get("asof")
        s = day.get("session")
        if a and s:
            out[str(a)] = str(s)
    return out


def infer_next_session(asof: str) -> str | None:
    """Next weekday after asof (US holidays ignored; display fallback only)."""
    try:
        d = datetime.strptime(str(asof)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.isoformat()


def resolve_session(asof: str | None, session_map: dict[str, str] | None = None) -> str | None:
    if not asof:
        return None
    key = str(asof)
    if session_map and key in session_map:
        return session_map[key]
    return infer_next_session(key)


def format_day_label(asof: str | None, session: str | None = None) -> str:
    """e.g. 10-07→08 (asof MM-DD → session DD)."""
    if not asof:
        return "—"
    a = str(asof)
    if len(a) < 10:
        return a
    left = f"{a[5:7]}-{a[8:10]}"
    s = str(session) if session else ""
    if len(s) >= 10:
        return f"{left}→{s[8:10]}"
    return left


def format_px(x: Any) -> str:
    if x is None:
        return "—"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    if v != v:  # NaN
        return "—"
    return f"{v:,.2f}"


def format_result_label(
    *,
    action: str | None,
    fill: dict | None,
    pending: bool,
) -> str:
    """Result cell: 勝/負 +%（出場）| 未入場 | 觀望 | 待結算. Never includes HKD."""
    if pending:
        return "待結算"
    act = (action or "").strip()
    if act == "觀望":
        return "觀望"
    if not act or act not in ("做多", "做空"):
        # Missing card / unknown — don't invent win/lose
        if fill is None:
            return "—"
    if fill is None:
        return "未入場"
    try:
        ret = float(fill.get("ret"))
    except (TypeError, ValueError):
        return "未入場"
    label = "勝" if ret > 0 else "負"
    sign = "+" if ret > 0 else "−"
    pct = f"{abs(ret) * 100:.2f}"
    reason_raw = str(fill.get("reason") or "")
    reason = REASON_ZH.get(reason_raw, reason_raw or "—")
    return f"{label} {sign}{pct}%（{reason}）"


def index_fills(fills: list[dict] | None) -> dict[tuple[str, str, str], dict]:
    """Key: (family, ticker_upper, asof) -> fill dict (last wins if dup)."""
    out: dict[tuple[str, str, str], dict] = {}
    for f in fills or []:
        fam = str(f.get("family") or "")
        ticker = str(f.get("ticker") or "").upper()
        asof = str(f.get("asof") or "")
        if not (fam and ticker and asof):
            continue
        out[(fam, ticker, asof)] = f
    return out


def is_asof_pending(asof: str | None, realized_asofs: list[str] | set[str] | None) -> bool:
    if not asof:
        return True
    realized = {str(x) for x in (realized_asofs or [])}
    return str(asof) not in realized


def build_two_day_row(
    *,
    asof: str | None,
    session: str | None,
    card: dict | None,
    fill: dict | None,
    pending: bool,
) -> dict[str, str]:
    action = (card or {}).get("action")
    return {
        "日": format_day_label(asof, session),
        "方向": str(action or "—"),
        "入場": format_px((card or {}).get("entry_px")) if action in ("做多", "做空") else "—",
        "止盈": format_px((card or {}).get("tp")) if action in ("做多", "做空") else "—",
        "止損": format_px((card or {}).get("sl")) if action in ("做多", "做空") else "—",
        "結果": format_result_label(action=action, fill=fill, pending=pending),
    }


def build_two_day_rows(
    *,
    family: str,
    ticker: str,
    today_asof: str | None,
    prev_asof: str | None,
    today_card: dict | None,
    prev_card: dict | None,
    fills_index: dict[tuple[str, str, str], dict],
    session_map: dict[str, str],
    realized_asofs: list[str] | set[str] | None,
) -> list[dict[str, str]]:
    """Prev row then today row (B-table order)."""
    t = str(ticker or "").upper()
    fam = str(family or "")
    prev_session = resolve_session(prev_asof, session_map) if prev_asof else None
    today_session = resolve_session(today_asof, session_map) if today_asof else None
    prev_fill = fills_index.get((fam, t, str(prev_asof))) if prev_asof else None
    today_fill = fills_index.get((fam, t, str(today_asof))) if today_asof else None
    rows: list[dict[str, str]] = []
    if prev_asof:
        rows.append(
            build_two_day_row(
                asof=prev_asof,
                session=prev_session,
                card=prev_card,
                fill=prev_fill,
                pending=is_asof_pending(prev_asof, realized_asofs),
            )
        )
    rows.append(
        build_two_day_row(
            asof=today_asof,
            session=today_session,
            card=today_card,
            fill=today_fill,
            pending=is_asof_pending(today_asof, realized_asofs),
        )
    )
    return rows
