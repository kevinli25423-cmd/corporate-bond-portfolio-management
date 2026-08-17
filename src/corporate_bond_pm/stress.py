from __future__ import annotations

import pandas as pd


def bond_stress_return(
    modified_duration: float,
    spread_duration: float,
    treasury_bp: float,
    spread_bp: float,
    liquidity_cost_bp: float,
    spread_multiplier: float = 1.0,
    liquidity_multiplier: float = 1.0,
) -> float:
    rates = -modified_duration * treasury_bp / 10000.0
    spreads = -spread_duration * (spread_bp * spread_multiplier) / 10000.0
    liquidity = -(liquidity_cost_bp * liquidity_multiplier) / 10000.0
    return rates + spreads + liquidity


def portfolio_stress(weights: pd.DataFrame, scenarios: dict) -> pd.DataFrame:
    rows = []
    for scenario, shock in scenarios.items():
        total = 0.0
        for _, r in weights.iterrows():
            if r["asset"] == "Cash":
                ret = 0.0
            else:
                ret = bond_stress_return(
                    r["modified_duration"],
                    r["spread_duration"],
                    shock["treasury_bp"],
                    shock["financial_oas_bp"],
                    shock["liquidity_cost_bp"],
                    r.get("stress_spread_multiplier", 1.0),
                    r.get("stress_liquidity_multiplier", 1.0),
                )
            total += r["weight"] * ret
        rows.append({
            "scenario": scenario,
            "portfolio_return": total,
            "portfolio_return_pct": total * 100.0,
        })
    return pd.DataFrame(rows)


def apply_portfolio_overlay(
    optimizer: pd.DataFrame,
    capped_asset: str,
    capped_weight: float,
    cash_target: float,
    defensive_asset: str,
) -> pd.DataFrame:
    """Apply a transparent concentration/liquidity overlay after the mathematical optimizer."""
    keep = [c for c in [
        "asset", "optimizer_weight", "modified_duration", "spread_duration",
        "stress_spread_multiplier", "stress_liquidity_multiplier",
    ] if c in optimizer.columns]
    x = optimizer[keep].copy().rename(columns={"optimizer_weight": "weight"})

    def set_weight(asset: str, target: float) -> float:
        idx = x.index[x["asset"].eq(asset)][0]
        old = float(x.loc[idx, "weight"])
        x.loc[idx, "weight"] = target
        return target - old

    total_delta = 0.0
    current_cap_asset = float(x.loc[x["asset"].eq(capped_asset), "weight"].iloc[0])
    if current_cap_asset > capped_weight:
        total_delta += set_weight(capped_asset, capped_weight)

    current_cash = float(x.loc[x["asset"].eq("Cash"), "weight"].iloc[0])
    if current_cash < cash_target:
        total_delta += set_weight("Cash", cash_target)

    idx = x.index[x["asset"].eq(defensive_asset)][0]
    x.loc[idx, "weight"] -= total_delta
    x["weight"] = x["weight"] / x["weight"].sum()
    return x
