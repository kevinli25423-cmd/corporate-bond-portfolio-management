from __future__ import annotations

import pandas as pd


def zscore_cross_section(s: pd.Series, higher_is_better: bool = True) -> pd.Series:
    std = s.std(ddof=0)
    z = (s - s.mean()) / (std if std > 0 else 1.0)
    return z if higher_is_better else -z


def build_fundamental_scorecard(f: pd.DataFrame) -> pd.DataFrame:
    """Transparent issuer comparison scorecard; it does not mechanically map score units to spread bp."""
    x = f.copy()
    x["cet1_buffer_pp"] = x["cet1_ratio_pct"] - x["required_cet1_pct"]

    x["capital_score"] = (
        0.70 * zscore_cross_section(x["cet1_buffer_pp"], True)
        + 0.30 * zscore_cross_section(x["tlac_buffer_pct"], True)
    )
    x["asset_quality_score"] = (
        0.55 * zscore_cross_section(x["nco_pct"], False)
        + 0.45 * zscore_cross_section(x["npl_pct"], False)
    )
    x["funding_score"] = (
        0.60 * zscore_cross_section(x["deposit_growth_pct"], True)
        + 0.40 * zscore_cross_section(x["lcr_pct"], True)
    )
    x["earnings_score"] = (
        0.60 * zscore_cross_section(x["rotce_pct"], True)
        + 0.40 * zscore_cross_section(x["ppnr_growth_pct"], True)
    )
    x["fundamental_score"] = (
        0.30 * x["capital_score"]
        + 0.25 * x["asset_quality_score"]
        + 0.25 * x["funding_score"]
        + 0.20 * x["earnings_score"]
    )
    x["credit_view"] = pd.cut(
        x["fundamental_score"],
        bins=[-float("inf"), -0.6, -0.1, 0.6, float("inf")],
        labels=["Moderate", "Moderate+", "Strong", "Very Strong"],
    ).astype(str)
    return x
