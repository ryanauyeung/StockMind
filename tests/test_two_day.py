"""Two-day B-table helpers."""

from __future__ import annotations

from stockmind.two_day import (
    build_two_day_rows,
    format_result_label,
    index_fills,
    resolve_pair_asofs,
    resolve_session,
)


def test_resolve_pair_asofs_newest_first():
    asofs = ["2026-10-08", "2026-10-07", "2026-10-06"]
    assert resolve_pair_asofs(asofs) == ("2026-10-07", "2026-10-08")
    assert resolve_pair_asofs(asofs, "2026-10-07") == ("2026-10-06", "2026-10-07")
    assert resolve_pair_asofs(asofs, "2026-10-06") == (None, "2026-10-06")


def test_format_result_no_hkd():
    win = format_result_label(
        action="做空",
        fill={"ret": 0.0060012584112483615, "reason": "tp", "pnl_hkd": 340.76},
        pending=False,
    )
    assert win == "勝 +0.60%（止盈出場）"
    assert "HK" not in win and "$" not in win

    lose = format_result_label(
        action="做空",
        fill={"ret": -0.002108518994936124, "reason": "close", "pnl_hkd": -139.76},
        pending=False,
    )
    assert lose == "負 −0.21%（收市平倉）"
    assert "HK" not in lose and "$" not in lose

    assert format_result_label(action="做空", fill=None, pending=False) == "未入場"
    assert format_result_label(action="觀望", fill=None, pending=False) == "觀望"
    assert format_result_label(action="做空", fill=None, pending=True) == "待結算"


def test_build_rows_brk_b_and_mu_style():
    fills = index_fills(
        [
            {
                "family": "stock",
                "ticker": "BRK-B",
                "asof": "2026-10-07",
                "ret": 0.0060012584112483615,
                "reason": "tp",
                "pnl_hkd": 340.76,
            }
        ]
    )
    session_map = {"2026-10-07": "2026-10-08"}
    realized = ["2026-10-07"]

    brk_prev = {
        "action": "做空",
        "entry_px": 509.3064797957777,
        "tp": 506.25,
        "sl": 514.3314758720891,
    }
    brk_today = {
        "action": "做空",
        "entry_px": 514.1604163980822,
        "tp": 511.04998779296875,
        "sl": 519.3239862571783,
    }
    rows = build_two_day_rows(
        family="stock",
        ticker="BRK-B",
        today_asof="2026-10-08",
        prev_asof="2026-10-07",
        today_card=brk_today,
        prev_card=brk_prev,
        fills_index=fills,
        session_map=session_map,
        realized_asofs=realized,
    )
    assert len(rows) == 2
    assert rows[0]["日"] == "10-07→08"
    assert rows[0]["結果"] == "勝 +0.60%（止盈出場）"
    assert "HK" not in rows[0]["結果"]
    assert rows[1]["結果"] == "待結算"
    assert rows[1]["方向"] == "做空"

    mu_rows = build_two_day_rows(
        family="stock",
        ticker="MU",
        today_asof="2026-10-08",
        prev_asof="2026-10-07",
        today_card={"action": "做空", "entry_px": 1060.88, "tp": 1035.84, "sl": 1105.67},
        prev_card={"action": "做空", "entry_px": 1108.19, "tp": 1088.0, "sl": 1154.28},
        fills_index=fills,
        session_map=session_map,
        realized_asofs=realized,
    )
    assert mu_rows[0]["結果"] == "未入場"
    assert mu_rows[1]["結果"] == "待結算"


def test_resolve_session_infers_weekday():
    assert resolve_session("2026-10-08", {}) == "2026-10-09"
    assert resolve_session("2026-10-09", {}) == "2026-10-12"  # Fri -> Mon
    assert resolve_session("2026-10-07", {"2026-10-07": "2026-10-08"}) == "2026-10-08"
