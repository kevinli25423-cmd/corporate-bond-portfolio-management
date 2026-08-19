from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from corporate_bond_pm.market_factor import fetch_fred_ig_oas, attach_ig_systematic_factor
from corporate_bond_pm.real_risk_decomposition import (
    add_factor_decomposition,
    build_cob_risk_snapshot,
    build_krd_snapshot,
    build_pair_risk_summary,
    build_stress_table,
)

PAIR_PATH = ROOT / "data/processed/real/citi_jpm_real_pair_daily.csv"
SCENARIO_PATH = ROOT / "config/citi_jpm_dashboard_scenario.json"
OUT_DIR = ROOT / "data/processed/real"
RESULT_DIR = ROOT / "docs/results/real"
FIG_DIR = ROOT / "docs/figures"


def _save(fig, name: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG_DIR / name, dpi=180, facecolor="white")
    plt.close(fig)


def save_figures(panel, risk, pair_risk, krd, stress) -> None:
    fig, ax = plt.subplots(figsize=(11, 5.2), facecolor="white")
    ax.plot(panel["date"], panel["CITI_representative_price"], label="CITI")
    ax.plot(panel["date"], panel["JPM_representative_price"], label="JPM")
    ax.set_title("Clean-Price History")
    ax.set_ylabel("Price per 100")
    ax.legend()
    ax.grid(alpha=0.20)
    _save(fig, "real_citi_jpm_price_history.png")

    fig, ax = plt.subplots(figsize=(11, 5.2), facecolor="white")
    ax.plot(panel["date"], panel["CITI_ytc_pct"], label="CITI YTC")
    ax.plot(panel["date"], panel["CITI_treasury_yield_pct"], label="CITI matched Treasury")
    ax.plot(panel["date"], panel["JPM_ytc_pct"], label="JPM YTC")
    ax.plot(panel["date"], panel["JPM_treasury_yield_pct"], label="JPM matched Treasury")
    ax.set_title("Yield to First Par Call vs Matched Treasury")
    ax.set_ylabel("Percent")
    ax.legend(ncol=2)
    ax.grid(alpha=0.20)
    _save(fig, "real_citi_jpm_ytc_treasury_history.png")

    rp = risk.set_index("issuer")[["dv01_usd_per_bp", "cs01_usd_per_bp"]]
    fig, ax = plt.subplots(figsize=(9.5, 5.0), facecolor="white")
    rp.plot(kind="bar", ax=ax)
    ax.set_title("DV01 and CS01 — per $10mm Face")
    ax.set_ylabel("USD per 1 bp")
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=0)
    ax.grid(axis="y", alpha=0.20)
    _save(fig, "real_citi_jpm_dv01_cs01.png")

    bp = risk.set_index("issuer")[
        ["treasury_change_bp", "systematic_credit_bp",
         "liquidity_contribution_bp", "idiosyncratic_credit_bp"]
    ].T
    bp.index = ["Rates", "Systematic credit proxy", "Liquidity", "Idiosyncratic credit"]
    fig, ax = plt.subplots(figsize=(10.5, 5.4), facecolor="white")
    bp.plot(kind="bar", ax=ax)
    ax.axhline(0.0, linewidth=1)
    ax.set_title("COB Yield-Change Factor Decomposition")
    ax.set_ylabel("Basis-point contribution")
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=16)
    ax.grid(axis="y", alpha=0.20)
    _save(fig, "real_citi_jpm_cob_bp_decomposition.png")

    pr = pair_risk.iloc[0]
    pnl = pd.Series({
        "Rates": pr["rate_pnl_usd"],
        "Systematic credit": pr["systematic_credit_pnl_usd"],
        "Liquidity": pr["liquidity_pnl_usd"],
        "Idiosyncratic": pr["idiosyncratic_credit_pnl_usd"],
        "Pricing residual": pr["pricing_residual_pnl_usd"],
    })
    fig, ax = plt.subplots(figsize=(10.5, 5.4), facecolor="white")
    pnl.plot(kind="bar", ax=ax)
    ax.axhline(0.0, linewidth=1)
    ax.set_title("Hypothetical DV01-Neutral Pair — COB P&L Explain")
    ax.set_ylabel("USD")
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=16)
    ax.grid(axis="y", alpha=0.20)
    _save(fig, "real_citi_jpm_pair_factor_pnl.png")

    tail = panel.tail(90)
    fig, ax = plt.subplots(figsize=(11, 5.2), facecolor="white")
    ax.plot(tail["date"], tail["CITI_idiosyncratic_credit_bp"], label="CITI idiosyncratic")
    ax.plot(tail["date"], tail["JPM_idiosyncratic_credit_bp"], label="JPM idiosyncratic")
    ax.plot(tail["date"], tail["systematic_credit_factor_change_bp"], label="IG systematic credit factor")
    ax.axhline(0.0, linewidth=1)
    ax.set_title("Recent Credit-Factor Changes")
    ax.set_ylabel("Basis points")
    ax.legend()
    ax.grid(alpha=0.20)
    _save(fig, "real_citi_jpm_credit_factor_history.png")

    fig, ax = plt.subplots(figsize=(11, 5.2), facecolor="white")
    for issuer in ("CITI", "JPM"):
        vol = pd.to_numeric(tail[f"{issuer}_displayed_volume"], errors="coerce")
        ratio = vol / vol.rolling(20, min_periods=5).median()
        ax.plot(tail["date"], ratio, label=f"{issuer} volume / 20-observation median")
    ax.axhline(1.0, linewidth=1)
    ax.set_title("Liquidity Proxy — Reported Volume Relative to Recent Median")
    ax.set_ylabel("Ratio")
    ax.legend()
    ax.grid(alpha=0.20)
    _save(fig, "real_citi_jpm_liquidity_proxy.png")

    krd_cols = [c for c in krd.columns if c.startswith("krd_")]
    kp = krd.set_index("issuer")[krd_cols].T
    kp.index = [c.replace("krd_", "").upper() for c in kp.index]
    fig, ax = plt.subplots(figsize=(9.5, 5.0), facecolor="white")
    kp.plot(kind="bar", ax=ax)
    ax.set_title("Approximate Key-Rate DV01 — per $10mm Face")
    ax.set_ylabel("USD per 1 bp")
    ax.set_xlabel("Treasury key-rate node")
    ax.tick_params(axis="x", rotation=0)
    ax.grid(axis="y", alpha=0.20)
    _save(fig, "real_citi_jpm_krd.png")

    fig, ax = plt.subplots(figsize=(10.5, 5.2), facecolor="white")
    stress.set_index("scenario")["pair_pnl_usd"].plot(kind="bar", ax=ax)
    ax.axhline(0.0, linewidth=1)
    ax.set_title("Reference Pair — Stress P&L")
    ax.set_ylabel("USD")
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=18)
    ax.grid(axis="y", alpha=0.20)
    _save(fig, "real_citi_jpm_pair_stress.png")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build CITI/JPM PM risk dashboard inputs")
    parser.add_argument("--pair", type=Path, default=PAIR_PATH)
    parser.add_argument("--scenario", type=Path, default=SCENARIO_PATH)
    args = parser.parse_args()

    if not args.pair.exists():
        raise SystemExit(
            f"Missing {args.pair}. Run `python scripts/build_real_citi_jpm_pair.py` first."
        )

    cfg = json.loads(args.scenario.read_text())
    panel = pd.read_csv(args.pair, parse_dates=["date"])
    ig_oas = fetch_fred_ig_oas(panel["date"].min(), panel["date"].max())
    panel = attach_ig_systematic_factor(panel, ig_oas)
    panel = add_factor_decomposition(
        panel,
        regression_window=int(cfg["risk_regression_window"]),
        min_regression_observations=int(cfg["risk_min_regression_observations"]),
    )
    risk = build_cob_risk_snapshot(
        panel,
        base_face_notional_usd=float(cfg["citi_face_usd"]),
    )
    krd = build_krd_snapshot(risk)
    pair_risk = build_pair_risk_summary(
        panel,
        risk,
        base_citi_face_usd=float(cfg["citi_face_usd"]),
    )
    stress = build_stress_table(pair_risk, risk, cfg["stress_scenarios"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    panel.to_csv(OUT_DIR / "citi_jpm_risk_decomposition_daily.csv", index=False)
    ig_oas.to_csv(OUT_DIR / "ig_oas_systematic_factor.csv", index=False)
    risk.to_csv(RESULT_DIR / "citi_jpm_risk_snapshot.csv", index=False)
    pair_risk.to_csv(RESULT_DIR / "citi_jpm_pair_risk_summary.csv", index=False)
    krd.to_csv(RESULT_DIR / "citi_jpm_krd_snapshot.csv", index=False)
    stress.to_csv(RESULT_DIR / "citi_jpm_pair_stress.csv", index=False)

    save_figures(panel, risk, pair_risk, krd, stress)

    print("PM risk analytics complete")
    print(f"COB date: {risk['as_of'].iloc[0]} vs {risk['prior_date'].iloc[0]}")
    print("\nCOB factor decomposition")
    print(risk[[
        "issuer", "ytc_change_bp", "treasury_change_bp", "spread_change_bp",
        "systematic_credit_bp", "liquidity_contribution_bp",
        "idiosyncratic_credit_bp", "dv01_usd_per_bp", "cs01_usd_per_bp",
        "volume_vs_20obs_median", "spread_change_volatility_20obs_bp"
    ]].to_string(index=False))
    print("\nReference pair risk")
    print(pair_risk.to_string(index=False))
    print("\nStress")
    print(stress[["scenario", "pair_pnl_usd"]].to_string(index=False))


if __name__ == "__main__":
    main()
