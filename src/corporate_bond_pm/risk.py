from __future__ import annotations

import numpy as np
import pandas as pd


def bond_dv01(market_value: float, modified_duration: float) -> float:
    return market_value * modified_duration * 1e-4


def bond_cs01(market_value: float, spread_duration: float) -> float:
    return market_value * spread_duration * 1e-4


def krd_weights(maturity_years: float) -> dict[str, float]:
    """Simple linear interpolation across key-rate nodes for a transparent research prototype."""
    nodes = np.array([2.0, 3.0, 5.0, 7.0, 10.0])
    if maturity_years <= nodes[0]:
        w = np.array([1, 0, 0, 0, 0], dtype=float)
    elif maturity_years >= nodes[-1]:
        w = np.array([0, 0, 0, 0, 1], dtype=float)
    else:
        hi = np.searchsorted(nodes, maturity_years)
        lo = hi - 1
        w = np.zeros(len(nodes))
        span = nodes[hi] - nodes[lo]
        w[lo] = (nodes[hi] - maturity_years) / span
        w[hi] = (maturity_years - nodes[lo]) / span
    return {f"krd_{int(n)}y": float(v) for n, v in zip(nodes, w)}


def build_risk_dashboard(
    holdings: pd.DataFrame,
    latest_market: pd.DataFrame,
    security_master: pd.DataFrame,
    portfolio_mv: float,
) -> pd.DataFrame:
    x = holdings.merge(latest_market, on=["security_id", "issuer"], how="left").merge(
        security_master[["security_id", "issuer", "maturity"]],
        on=["security_id", "issuer"],
        how="left",
    )
    x["market_value"] = x["weight"] * portfolio_mv
    x["dv01"] = x.apply(lambda r: bond_dv01(r["market_value"], r["modified_duration"]), axis=1)
    x["cs01"] = x.apply(lambda r: bond_cs01(r["market_value"], r["spread_duration"]), axis=1)
    as_of = latest_market["date"].max()
    x["maturity_years"] = (x["maturity"] - as_of).dt.days.clip(lower=1) / 365.25

    krd_cols: list[str] = []
    for idx, row in x.iterrows():
        for col, weight in krd_weights(row["maturity_years"]).items():
            x.loc[idx, col] = row["dv01"] * weight
            krd_cols.append(col)

    out_cols = [
        "security_id", "issuer", "weight", "market_value",
        "modified_duration", "spread_duration", "dv01", "cs01",
    ] + sorted(set(krd_cols))
    return x[out_cols]
