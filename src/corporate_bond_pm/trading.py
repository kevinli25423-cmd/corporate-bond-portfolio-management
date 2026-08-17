from __future__ import annotations

import pandas as pd


def build_trade_blotter(
    current: pd.DataFrame,
    final: pd.DataFrame,
    portfolio_mv: float,
    min_trade_dollars: float = 250_000,
) -> pd.DataFrame:
    c = current.set_index("asset")["weight"]
    f = final.set_index("asset")["weight"]
    rows = []
    for asset in f.index:
        delta = float(f[asset] - c.get(asset, 0.0))
        dollars = delta * portfolio_mv
        if abs(dollars) < min_trade_dollars:
            continue
        rows.append({
            "asset": asset,
            "side": "BUY" if dollars > 0 else "SELL/REDUCE",
            "trade_amount": abs(dollars),
            "weight_change_pct": delta * 100.0,
            "primary_objective": "Liquidity buffer" if asset == "Cash" else "Relative value / portfolio positioning",
        })
    if not rows:
        return pd.DataFrame(columns=["asset", "side", "trade_amount", "weight_change_pct", "primary_objective"])
    return pd.DataFrame(rows).sort_values("trade_amount", ascending=False)


def duration_neutral_reduce_amount(
    buy_amount: float,
    buy_dv01_per_mm: float,
    sell_dv01_per_mm: float,
) -> float:
    return buy_amount * buy_dv01_per_mm / sell_dv01_per_mm
