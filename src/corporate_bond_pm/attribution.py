from __future__ import annotations

import pandas as pd


def one_month_attribution(
    market_daily: pd.DataFrame,
    holdings: pd.DataFrame,
    portfolio_mv: float,
) -> pd.DataFrame:
    """Transparent one-month decomposition into rates, common spread, issuer/RV, carry, and roll-down."""
    dates = sorted(market_daily["date"].unique())
    if len(dates) < 22:
        raise ValueError("Need at least 22 business days for one-month attribution")
    start, end = pd.Timestamp(dates[-22]), pd.Timestamp(dates[-1])

    m0 = market_daily.loc[market_daily["date"].eq(start)].set_index("security_id")
    m1 = market_daily.loc[market_daily["date"].eq(end)].set_index("security_id")
    spread_moves = (m1["oas_bp"] - m0["oas_bp"]).rename("d_oas")
    market_spread_move = float(spread_moves.mean())

    totals = {"Rates": 0.0, "Market Spread": 0.0, "Issuer/RV": 0.0, "Carry": 0.0, "Roll-down": 0.0}
    for _, h in holdings.iterrows():
        sec = h["security_id"]
        if sec not in m0.index or sec not in m1.index:
            continue
        mv = h["weight"] * portfolio_mv
        dy_bp = (m1.loc[sec, "treasury_yield_pct"] - m0.loc[sec, "treasury_yield_pct"]) * 100.0
        d_oas = float(spread_moves.loc[sec])
        totals["Rates"] += -m0.loc[sec, "modified_duration"] * dy_bp / 10000.0 * mv
        totals["Market Spread"] += -m0.loc[sec, "spread_duration"] * market_spread_move / 10000.0 * mv
        totals["Issuer/RV"] += -m0.loc[sec, "spread_duration"] * (d_oas - market_spread_move) / 10000.0 * mv
        totals["Carry"] += m0.loc[sec, "carry_1m_bp"] / 10000.0 * mv
        totals["Roll-down"] += m0.loc[sec, "rolldown_1m_bp"] / 10000.0 * mv

    rows = [{"driver": k, "pnl": v} for k, v in totals.items()]
    rows.append({"driver": "Total", "pnl": sum(totals.values())})
    return pd.DataFrame(rows)
