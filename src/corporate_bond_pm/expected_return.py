from __future__ import annotations

import pandas as pd


def expected_return_from_rv(
    rv_bp: float,
    spread_duration: float,
    carry_1m_bp: float,
    rolldown_1m_bp: float,
    transaction_cost_bp: float,
    convergence_ratio: float,
    rates_view_bp: float = 0.0,
) -> dict:
    expected_spread_move_bp = -convergence_ratio * rv_bp
    convergence_return_bp = -spread_duration * expected_spread_move_bp
    total_bp = carry_1m_bp + rolldown_1m_bp + convergence_return_bp + rates_view_bp - transaction_cost_bp
    return {
        "expected_spread_move_bp": expected_spread_move_bp,
        "convergence_return_bp": convergence_return_bp,
        "expected_return_1m_bp": total_bp,
        "expected_return_1m_decimal": total_bp / 10000.0,
    }


def add_expected_returns(
    rv_dashboard: pd.DataFrame,
    convergence_ratio: float,
    transaction_cost_bp: float,
) -> pd.DataFrame:
    rows = []
    for _, r in rv_dashboard.iterrows():
        rows.append(expected_return_from_rv(
            rv_bp=r["blended_rv_bp"],
            spread_duration=r["spread_duration"],
            carry_1m_bp=r["carry_1m_bp"],
            rolldown_1m_bp=r["rolldown_1m_bp"],
            transaction_cost_bp=transaction_cost_bp,
            convergence_ratio=convergence_ratio,
        ))
    return pd.concat([rv_dashboard.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
