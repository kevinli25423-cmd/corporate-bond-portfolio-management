from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize


def estimate_monthly_covariance(market_daily: pd.DataFrame, securities: list[str]) -> pd.DataFrame:
    x = market_daily.loc[market_daily["security_id"].isin(securities)].copy()
    x = x.sort_values(["security_id", "date"])
    x["d_y_bp"] = x.groupby("security_id")["treasury_yield_pct"].diff() * 100.0
    x["d_oas_bp"] = x.groupby("security_id")["oas_bp"].diff()
    x["daily_return"] = -(
        x["modified_duration"] * x["d_y_bp"]
        + x["spread_duration"] * x["d_oas_bp"]
    ) / 10000.0
    panel = x.pivot(index="date", columns="security_id", values="daily_return").dropna()
    cov = panel.cov() * 21.0
    return cov.reindex(index=securities, columns=securities).fillna(0.0)


def optimize_portfolio(
    assets: pd.DataFrame,
    covariance: pd.DataFrame,
    current_weights: pd.Series,
    issuer_max_weight: float,
    cash_min_weight: float,
    duration_min: float,
    duration_max: float,
    risk_aversion: float,
    turnover_penalty: float,
) -> pd.DataFrame:
    names = assets["asset"].tolist()
    alpha = assets.set_index("asset").loc[names, "expected_return_1m_decimal"].to_numpy(float)
    duration = assets.set_index("asset").loc[names, "modified_duration"].to_numpy(float)
    w0 = current_weights.reindex(names).fillna(0.0).to_numpy(float)
    sigma = covariance.reindex(index=names, columns=names).fillna(0.0).to_numpy(float)

    def objective(w: np.ndarray) -> float:
        expected = w @ alpha
        risk = w @ sigma @ w
        turnover = np.sqrt((w - w0) ** 2 + 1e-8).sum()
        return -(expected - risk_aversion * risk - turnover_penalty * turnover / 12.0)

    constraints = [
        {"type": "eq", "fun": lambda w: w.sum() - 1.0},
        {"type": "ineq", "fun": lambda w: w @ duration - duration_min},
        {"type": "ineq", "fun": lambda w: duration_max - w @ duration},
    ]

    cash_idx = names.index("Cash")
    constraints.append({"type": "ineq", "fun": lambda w, i=cash_idx: w[i] - cash_min_weight})

    bounds = [
        (cash_min_weight, 0.40) if n == "Cash" else (0.0, issuer_max_weight)
        for n in names
    ]

    result = minimize(
        objective,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 2000, "ftol": 1e-12},
    )
    if not result.success:
        raise RuntimeError(f"Optimizer failed: {result.message}")

    out = assets.copy()
    out["current_weight"] = w0
    out["optimizer_weight"] = result.x
    out["weight_change"] = out["optimizer_weight"] - out["current_weight"]
    return out
