from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error


def historical_pair_signal(
    market_daily: pd.DataFrame,
    sec_a: str,
    sec_b: str,
    window: int = 252,
    min_history: int = 60,
) -> pd.DataFrame:
    """Compute a lagged rolling z-score so today's spread does not enter its own benchmark."""
    x = market_daily.loc[
        market_daily["security_id"].isin([sec_a, sec_b]),
        ["date", "security_id", "oas_bp"],
    ]
    p = x.pivot(index="date", columns="security_id", values="oas_bp").dropna()
    p["pair_spread_bp"] = p[sec_a] - p[sec_b]
    prior = p["pair_spread_bp"].shift(1)
    p["hist_mean_bp"] = prior.rolling(window, min_periods=min_history).mean()
    p["hist_std_bp"] = prior.rolling(window, min_periods=min_history).std(ddof=1)
    p["hist_z"] = (p["pair_spread_bp"] - p["hist_mean_bp"]) / p["hist_std_bp"]
    return p.reset_index()


def fair_pair_differential(
    oas_a: float,
    oas_b: float,
    cds_a: float,
    cds_b: float,
    duration_adj_bp: float = 0.0,
    liquidity_adj_bp: float = 0.0,
    structure_adj_bp: float = 0.0,
) -> dict:
    market_diff = oas_a - oas_b
    credit_diff = cds_a - cds_b
    bond_adj = duration_adj_bp + liquidity_adj_bp + structure_adj_bp
    fair_diff = credit_diff + bond_adj
    return {
        "market_diff_bp": market_diff,
        "credit_diff_bp": credit_diff,
        "bond_liquidity_adj_bp": bond_adj,
        "fair_diff_bp": fair_diff,
        "rv_residual_bp": market_diff - fair_diff,
    }


def fit_cross_sectional_fair_oas(
    market: pd.DataFrame,
    cds: pd.DataFrame,
    liquidity: pd.DataFrame,
    security_master: pd.DataFrame,
    train_days: int = 120,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pooled rolling-window regression used as a relative-value confirmation signal."""
    merged = (
        market.merge(cds, on=["date", "issuer"], how="left")
        .merge(liquidity, on=["date", "security_id"], how="left")
        .merge(
            security_master[["security_id", "issue_size_mm", "issue_date"]],
            on="security_id",
            how="left",
        )
    )
    merged["issue_age_years"] = (merged["date"] - merged["issue_date"]).dt.days / 365.25
    merged["log_oas"] = np.log(merged["oas_bp"].clip(lower=1.0))
    merged["log_cds"] = np.log(merged["cds_5y_bp"].clip(lower=1.0))

    latest = merged["date"].max()
    cutoff = latest - pd.offsets.BDay(train_days)
    train = merged.loc[(merged["date"] < latest) & (merged["date"] >= cutoff)].dropna().copy()
    test = merged.loc[merged["date"].eq(latest)].dropna().copy()

    features = ["log_cds", "spread_duration", "liquidity_score", "issue_age_years", "issue_size_mm"]
    model = LinearRegression().fit(train[features], train["log_oas"])
    train_pred = np.exp(model.predict(train[features]))
    test["regression_fair_oas_bp"] = np.exp(model.predict(test[features]))
    test["regression_rv_bp"] = test["oas_bp"] - test["regression_fair_oas_bp"]

    diagnostics = pd.DataFrame({
        "metric": ["train_mae_bp", "train_rows", "train_start", "train_end", "test_date"],
        "value": [
            mean_absolute_error(train["oas_bp"], train_pred),
            len(train),
            str(train["date"].min().date()),
            str(train["date"].max().date()),
            str(latest.date()),
        ],
    })
    return test, diagnostics
