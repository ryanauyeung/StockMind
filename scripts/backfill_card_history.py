#!/usr/bin/env python3
"""Backfill data/artifacts/history/ from git commits of cards_*.json (unique asof)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HIST = ROOT / "data" / "artifacts" / "history"
FAMILIES = {
    "shared": "cards_shared.json",
    "sector": "cards_sector.json",
    "stock": "cards_stock.json",
}


def main() -> int:
    log = subprocess.check_output(
        ["git", "log", "--pretty=format:%H", "--", "data/artifacts/cards_shared.json"],
        cwd=ROOT,
        text=True,
    ).strip()
    shas = log.splitlines() if log else []
    seen: set[str] = set()
    index: list[dict] = []
    for sha in shas:
        try:
            raw = subprocess.check_output(
                ["git", "show", f"{sha}:data/artifacts/cards_shared.json"],
                cwd=ROOT,
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            continue
        data = json.loads(raw)
        asof = data.get("asof")
        if not asof or asof in seen:
            continue
        seen.add(asof)
        day_dir = HIST / asof
        day_dir.mkdir(parents=True, exist_ok=True)
        families: dict = {}
        for fam, fname in FAMILIES.items():
            try:
                raw_f = subprocess.check_output(
                    ["git", "show", f"{sha}:data/artifacts/{fname}"],
                    cwd=ROOT,
                    text=True,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                continue
            payload = json.loads(raw_f)
            (day_dir / fname).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            families[fam] = {
                "file": f"history/{asof}/{fname}",
                "n_cards": payload.get("n_cards"),
                "n_long": payload.get("n_long"),
                "n_short": payload.get("n_short"),
                "n_flat": payload.get("n_flat"),
            }
        index.append(
            {
                "asof": asof,
                "commit": sha,
                "generated_at_utc": data.get("generated_at_utc"),
                "families": families,
            }
        )
        print(f"indexed {asof} families={list(families)}")
    HIST.mkdir(parents=True, exist_ok=True)
    (HIST / "index.json").write_text(
        json.dumps(
            {
                "version": 1,
                "source": "git backfill of cards_*.json unique asof (latest commit per asof)",
                "asofs": index,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {HIST / 'index.json'} n={len(index)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
