from __future__ import annotations

from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from corporate_bond_pm.data import load_project_data, latest_snapshot, point_in_time_fundamentals
from corporate_bond_pm.fundamentals import build_fundamental_scorecard
from corporate_bond_pm.relative_value import historical_pair_signal, fair_pair_differential, fit_cross_sectional_fair_oas
from corporate_bond_pm.expected_return import add_expected_returns
from corporate_bond_pm.risk import build_risk_dashboard
from corporate_bond_pm.optimizer import estimate_monthly_covariance, optimize_portfolio
from corporate_bond_pm.stress import portfolio_stress, apply_portfolio_overlay
from corporate_bond_pm.trading import build_trade_blotter
from corporate_bond_pm.attribution import one_month_attribution

OUT = ROOT / "data" / "output"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    data = load_project_data(ROOT)
    cfg = data.config
    latest = latest_snapshot(data.market_daily)
    as_of = latest["date"].max()

    scorecard = build_fundamental_scorecard(point_in_time_fundamentals(data.fundamentals, as_of))
    scorecard.to_csv(OUT / "fundamental_scorecard.csv", index=False)

    reps = data.security_master.loc[data.security_master["representative"]].set_index("issuer")["security_id"].to_dict()
    latest_rep = latest.loc[latest["security_id"].isin(reps.values())].copy()
    latest_cds = latest_snapshot(data.cds_daily).set_index("issuer")
    latest_liq = latest_snapshot(data.liquidity_daily).set_index("security_id")

    reg_latest, reg_diag = fit_cross_sectional_fair_oas(
        data.market_daily,
        data.cds_daily,
        data.liquidity_daily,
        data.security_master,
    )
    reg_map = reg_latest.set_index("security_id")["regression_rv_bp"]
    reg_diag.to_csv(OUT / "regression_diagnostics.csv", index=False)

    rows = []
    for issuer, sec in reps.items():
        m = latest_rep.loc[latest_rep["security_id"].eq(sec)].iloc[0]
        peer_issuer = "JPM" if issuer != "JPM" else "BAC"
        peer = reps[peer_issuer]
        peer_m = latest_rep.loc[latest_rep["security_id"].eq(peer)].iloc[0]

        pair = historical_pair_signal(
            data.market_daily,
            sec,
            peer,
            cfg["historical_window"],
            cfg["min_history"],
        )
        p = pair.iloc[-1]

        liquidity_adj = (latest_liq.loc[peer, "liquidity_score"] - latest_liq.loc[sec, "liquidity_score"]) * 8.0
        duration_adj = (m["spread_duration"] - peer_m["spread_duration"]) * 0.5
        fair = fair_pair_differential(
            m["oas_bp"],
            peer_m["oas_bp"],
            latest_cds.loc[issuer, "cds_5y_bp"],
            latest_cds.loc[peer_issuer, "cds_5y_bp"],
            duration_adj_bp=duration_adj,
            liquidity_adj_bp=liquidity_adj,
        )
        model_rv = float(reg_map.get(sec, 0.0))
        hist_component = (p["pair_spread_bp"] - p["hist_mean_bp"]) if pd.notna(p["hist_mean_bp"]) else 0.0
        blended = 0.50 * fair["rv_residual_bp"] + 0.25 * hist_component + 0.25 * model_rv
        fs = scorecard.loc[scorecard["issuer"].eq(issuer)].iloc[0]

        rows.append({
            "asset": issuer,
            "security_id": sec,
            "issuer": issuer,
            "credit_view": fs["credit_view"],
            "fundamental_score": fs["fundamental_score"],
            "oas_bp": m["oas_bp"],
            "cds_5y_bp": latest_cds.loc[issuer, "cds_5y_bp"],
            "hist_pair_z": p["hist_z"],
            "hist_component_bp": hist_component,
            "cds_bond_rv_bp": fair["rv_residual_bp"],
            "regression_rv_bp": model_rv,
            "blended_rv_bp": blended,
            "modified_duration": m["modified_duration"],
            "spread_duration": m["spread_duration"],
            "carry_1m_bp": m["carry_1m_bp"],
            "rolldown_1m_bp": m["rolldown_1m_bp"],
            "liquidity_score": latest_liq.loc[sec, "liquidity_score"],
        })

    rv = pd.DataFrame(rows)
    rv = add_expected_returns(rv, cfg["convergence_ratio"], cfg["transaction_cost_bp"])
    rv["action"] = pd.cut(
        rv["blended_rv_bp"],
        [-float("inf"), -1.5, 1.5, float("inf")],
        labels=["Reduce", "Hold", "Add"],
    ).astype(str)
    rv.to_csv(OUT / "rv_dashboard.csv", index=False)

    current_bonds = data.holdings.loc[data.holdings["asset"].ne("Cash")].copy()
    risk = build_risk_dashboard(current_bonds, latest, data.security_master, cfg["portfolio_market_value"])
    risk.to_csv(OUT / "risk_dashboard.csv", index=False)

    assets = rv[["asset", "expected_return_1m_decimal", "modified_duration", "spread_duration"]].copy()
    assets["stress_spread_multiplier"] = assets["asset"].map(cfg["stress_spread_multipliers"])
    assets["stress_liquidity_multiplier"] = assets["asset"].map(cfg["stress_liquidity_multipliers"])
    cash = pd.DataFrame([{
        "asset": "Cash",
        "expected_return_1m_decimal": 0.0035 / 12.0,
        "modified_duration": 0.0,
        "spread_duration": 0.0,
        "stress_spread_multiplier": 0.0,
        "stress_liquidity_multiplier": 0.0,
    }])
    assets = pd.concat([assets, cash], ignore_index=True)

    current_weights = data.holdings.set_index("asset")["weight"]
    cov_bonds = estimate_monthly_covariance(data.market_daily, [reps[k] for k in ["JPM", "BAC", "C", "WFC"]])
    rename = {reps[k]: k for k in reps}
    cov_bonds = cov_bonds.rename(index=rename, columns=rename)
    cov = pd.DataFrame(0.0, index=assets["asset"], columns=assets["asset"])
    cov.loc[cov_bonds.index, cov_bonds.columns] = cov_bonds
    cov.loc["Cash", "Cash"] = 1e-8

    opt = optimize_portfolio(
        assets,
        cov,
        current_weights,
        cfg["issuer_max_weight"],
        cfg["cash_min_weight"],
        cfg["duration_min"],
        cfg["duration_max"],
        cfg["risk_aversion"],
        cfg["turnover_penalty"],
    )
    opt.to_csv(OUT / "portfolio_optimizer.csv", index=False)

    current = assets.copy()
    current["weight"] = current["asset"].map(current_weights)
    current.to_csv(OUT / "portfolio_current.csv", index=False)

    final = apply_portfolio_overlay(
        opt,
        capped_asset=cfg["overlay_asset"],
        capped_weight=cfg["overlay_asset_cap"],
        cash_target=cfg["overlay_cash_target"],
        defensive_asset=cfg["overlay_defensive_asset"],
    )
    final.to_csv(OUT / "portfolio_final.csv", index=False)

    stress_frames = []
    portfolios = [
        ("Current", current[["asset", "weight", "modified_duration", "spread_duration", "stress_spread_multiplier", "stress_liquidity_multiplier"]]),
        ("Optimizer", opt.rename(columns={"optimizer_weight": "weight"})[["asset", "weight", "modified_duration", "spread_duration", "stress_spread_multiplier", "stress_liquidity_multiplier"]]),
        ("Final", final),
    ]
    for label, weights in portfolios:
        s = portfolio_stress(weights, cfg["stress_scenarios"])
        s.insert(0, "portfolio", label)
        stress_frames.append(s)
    stress = pd.concat(stress_frames, ignore_index=True)
    stress.to_csv(OUT / "stress_results.csv", index=False)

    blotter = build_trade_blotter(current, final, cfg["portfolio_market_value"])
    blotter.to_csv(OUT / "trade_blotter.csv", index=False)

    attribution = one_month_attribution(data.market_daily, current_bonds, cfg["portfolio_market_value"])
    attribution.to_csv(OUT / "attribution.csv", index=False)

    print("Pipeline complete")
    print("\nRelative-value dashboard:")
    print(rv[["asset", "credit_view", "oas_bp", "hist_pair_z", "blended_rv_bp", "expected_return_1m_bp", "action"]].round(2).to_string(index=False))
    print("\nPortfolio weights:")
    print(opt[["asset", "current_weight", "optimizer_weight", "weight_change"]].round(4).to_string(index=False))
    print("\nStress results (%):")
    print(stress[["portfolio", "scenario", "portfolio_return_pct"]].round(2).to_string(index=False))
    print(f"\nOutputs written to {OUT}")


if __name__ == "__main__":
    main()
