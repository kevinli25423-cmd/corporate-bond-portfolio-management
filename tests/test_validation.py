from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from corporate_bond_pm.validation import (
    build_pair_validation_panel,
    independent_event_backtest,
)


def _mini_market() -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=10)
    rows = []
    a = [10, 10, 10, 14, 13, 12, 11, 10, 10, 10]
    b = [8] * 10
    for date, a_oas, b_oas in zip(dates, a, b):
        rows.append({"date": date, "security_id": "A", "oas_bp": a_oas, "spread_duration": 4.0})
        rows.append({"date": date, "security_id": "B", "oas_bp": b_oas, "spread_duration": 4.0})
    return pd.DataFrame(rows)


def test_validation_uses_future_only_for_outcome() -> None:
    panel = build_pair_validation_panel(
        _mini_market(),
        "A",
        "B",
        window=3,
        min_history=2,
        horizons=(1,),
    )
    # On the widening day, the historical benchmark is based on prior pair spreads.
    widening = panel.loc[panel["date"].eq(pd.Timestamp("2026-01-06"))].iloc[0]
    assert widening["hist_mean_bp"] == 2.0
    assert widening["pair_spread_bp"] == 6.0


def test_independent_event_backtest_blocks_overlapping_entries() -> None:
    panel = build_pair_validation_panel(
        _mini_market(),
        "A",
        "B",
        window=3,
        min_history=2,
        horizons=(2,),
    )
    events, summary = independent_event_backtest(
        panel,
        signal_threshold=1.0,
        horizon_days=2,
        pair_transaction_cost_bp=0.0,
    )
    assert len(events) == int(summary.loc[0, "events"])
    if len(events) > 1:
        gaps = events["date"].diff().dropna().dt.days
        assert (gaps >= 2).all()
