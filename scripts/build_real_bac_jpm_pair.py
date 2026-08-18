from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from corporate_bond_pm.bond_math import FixedToFloatBond, yield_to_call_from_clean_price
from corporate_bond_pm.trace_real import load_finra_trade_export, daily_trade_summary
from corporate_bond_pm.treasury_real import fetch_treasury_yield_curve_range, attach_treasury_proxy

CONFIG = ROOT / "config" / "real_bac_jpm_pair.json"
OUT_DIR = ROOT / "data" / "processed" / "real"
RESULT_DIR = ROOT / "docs" / "results" / "real"
FIG_DIR = ROOT / "docs" / "figures"


def build_security_daily(path: Path, terms: dict, representative: str, args) -> pd.DataFrame:
    trades = load_finra_trade_export(path, date_col=args.date_col, price_col=args.price_col, volume_col=args.volume_col)
    daily = daily_trade_summary(trades, representative=representative)
    bond = FixedToFloatBond.from_dict(terms)
    daily = daily.loc[daily["date"] < pd.Timestamp(bond.first_par_call_date)].copy()
    daily["ytc_pct"] = [100.0 * yield_to_call_from_clean_price(bond, d.date(), p) for d, p in zip(daily["date"], daily["representative_price"])]
    daily["issuer"] = terms["issuer"]
    daily["cusip"] = terms["cusip"]
    return daily


def add_lagged_zscore(pair: pd.DataFrame, window: int) -> pd.DataFrame:
    x = pair.copy()
    lagged = x["pair_spread_bp"].shift(1)
    x["hist_mean_bp"] = lagged.rolling(window, min_periods=window).mean()
    x["hist_std_bp"] = lagged.rolling(window, min_periods=window).std(ddof=1)
    x["hist_z"] = (x["pair_spread_bp"] - x["hist_mean_bp"]) / x["hist_std_bp"]
    return x


def add_forward_validation(pair: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    x = pair.copy()
    direction = np.sign(x["hist_z"])
    for h in horizons:
        future_change = x["pair_spread_bp"].shift(-h) - x["pair_spread_bp"]
        x[f"future_pair_change_{h}obs_bp"] = future_change
        x[f"signed_convergence_{h}obs_bp"] = -direction * future_change
    return x


def save_figures(pair: pd.DataFrame) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5.4))
    ax.plot(pair["date"], pair["BAC_proxy_spread_bp"], label="BAC proxy spread")
    ax.plot(pair["date"], pair["JPM_proxy_spread_bp"], label="JPM proxy spread")
    ax.set_title("Real TRACE / Treasury Public-Data Spread Proxies")
    ax.set_ylabel("YTC − interpolated Treasury (bp)")
    ax.legend(); ax.grid(alpha=0.25); fig.tight_layout()
    fig.savefig(FIG_DIR / "real_bac_jpm_proxy_spreads.png", dpi=160); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5.4))
    ax.plot(pair["date"], pair["pair_spread_bp"], label="BAC − JPM")
    if pair["hist_mean_bp"].notna().any(): ax.plot(pair["date"], pair["hist_mean_bp"], label="Lagged 252-observation mean")
    ax.axhline(0.0, linewidth=1); ax.set_title("Real BAC − JPM Public Spread Differential"); ax.set_ylabel("Basis points")
    ax.legend(); ax.grid(alpha=0.25); fig.tight_layout()
    fig.savefig(FIG_DIR / "real_bac_jpm_pair_spread.png", dpi=160); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5.4))
    ax.plot(pair["date"], pair["hist_z"]); ax.axhline(0.0, linewidth=1); ax.axhline(2.0, linestyle="--", linewidth=1); ax.axhline(-2.0, linestyle="--", linewidth=1)
    ax.set_title("Real BAC − JPM Lagged Historical Z-Score"); ax.set_ylabel("Z-score"); ax.grid(alpha=0.25); fig.tight_layout()
    fig.savefig(FIG_DIR / "real_bac_jpm_zscore.png", dpi=160); plt.close(fig)


def write_summary(pair: pd.DataFrame, cfg: dict) -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    valid = pair.dropna(subset=["hist_z"])
    if valid.empty:
        latest_text = "A full 252-observation lagged z-score is not yet available in the aligned trade sample."
    else:
        r = valid.iloc[-1]
        latest_text = (
            f"Latest fully formed signal date: **{r['date'].date()}**. BAC proxy spread: **{r['BAC_proxy_spread_bp']:.2f} bp**; "
            f"JPM proxy spread: **{r['JPM_proxy_spread_bp']:.2f} bp**; pair differential: **{r['pair_spread_bp']:.2f} bp**; "
            f"lagged z-score: **{r['hist_z']:.2f}σ**."
        )
    rows = []
    for h in cfg["forward_horizons"]:
        col = f"signed_convergence_{h}obs_bp"
        x = valid.loc[valid["hist_z"].abs() >= 1.0].dropna(subset=[col])
        rows.append(f"| {h} observations | {len(x)} | " + ("n/a | n/a |" if x.empty else f"{x[col].mean():.2f} bp | {(x[col] > 0).mean():.1%} |"))
    md = f'''# V2 Step 1 — Real BAC/JPM Public-Data Pair

This module replaces the synthetic pair-spread input with actual secondary-market transaction prices exported from FINRA's public fixed-income interface and official U.S. Treasury daily par-yield data.

## Latest result

{latest_text}

![Real public-data proxy spreads](../../figures/real_bac_jpm_proxy_spreads.png)

![Real pair spread](../../figures/real_bac_jpm_pair_spread.png)

![Real lagged z-score](../../figures/real_bac_jpm_zscore.png)

## Chronological validation

| Horizon | Signal observations (`|Z|>=1`) | Avg signed convergence | Hit rate |
|---|---:|---:|---:|
{chr(10).join(rows)}

## Public spread definition

`proxy spread = yield to first par call − Treasury yield interpolated to the first par-call date`.

This is deliberately not labeled OAS.
'''
    (RESULT_DIR / "real_bac_jpm_step1.md").write_text(md, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build real BAC/JPM public-data relative-value pair")
    parser.add_argument("--jpm", type=Path, default=ROOT / "data/raw/trace/JPM_46647PEU6.csv")
    parser.add_argument("--bac", type=Path, default=ROOT / "data/raw/trace/BAC_06051GMT3.csv")
    parser.add_argument("--date-col", default=None); parser.add_argument("--price-col", default=None); parser.add_argument("--volume-col", default=None)
    args = parser.parse_args()
    cfg = json.loads(CONFIG.read_text())
    missing = [p for p in [args.jpm, args.bac] if not p.exists()]
    if missing:
        raise SystemExit("Missing FINRA CSV export(s):\n  " + "\n  ".join(str(p) for p in missing) + "\nSee docs/real_data_step1.md for export instructions.")

    representative = cfg.get("price_method", "median")
    jpm = build_security_daily(args.jpm, cfg["securities"]["JPM"], representative, args)
    bac = build_security_daily(args.bac, cfg["securities"]["BAC"], representative, args)
    treasury = fetch_treasury_yield_curve_range(min(jpm["date"].min(), bac["date"].min()), max(jpm["date"].max(), bac["date"].max()))
    jpm = attach_treasury_proxy(jpm, treasury, call_date=cfg["securities"]["JPM"]["first_par_call_date"])
    bac = attach_treasury_proxy(bac, treasury, call_date=cfg["securities"]["BAC"]["first_par_call_date"])
    for x in (jpm, bac): x["proxy_spread_bp"] = (x["ytc_pct"] - x["treasury_yield_pct"]) * 100.0

    j = jpm[["date", "representative_price", "trade_count", "displayed_volume", "ytc_pct", "treasury_yield_pct", "proxy_spread_bp"]].rename(columns={c: f"JPM_{c}" for c in ["representative_price", "trade_count", "displayed_volume", "ytc_pct", "treasury_yield_pct", "proxy_spread_bp"]})
    b = bac[["date", "representative_price", "trade_count", "displayed_volume", "ytc_pct", "treasury_yield_pct", "proxy_spread_bp"]].rename(columns={c: f"BAC_{c}" for c in ["representative_price", "trade_count", "displayed_volume", "ytc_pct", "treasury_yield_pct", "proxy_spread_bp"]})
    pair = b.merge(j, on="date", how="inner").sort_values("date").reset_index(drop=True)
    pair["pair_spread_bp"] = pair["BAC_proxy_spread_bp"] - pair["JPM_proxy_spread_bp"]
    pair = add_forward_validation(add_lagged_zscore(pair, int(cfg["historical_window"])), list(cfg["forward_horizons"]))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pair.to_csv(OUT_DIR / "bac_jpm_real_pair_daily.csv", index=False); jpm.to_csv(OUT_DIR / "jpm_46647peu6_daily.csv", index=False); bac.to_csv(OUT_DIR / "bac_06051gmt3_daily.csv", index=False); treasury.to_csv(OUT_DIR / "treasury_curve_daily.csv", index=False)
    save_figures(pair); write_summary(pair, cfg)
    print("V2 Step 1 real-data pair complete"); print(f"Aligned pair observations: {len(pair)}")
    valid = pair.dropna(subset=["hist_z"])
    if not valid.empty:
        r = valid.iloc[-1]; print(f"Latest signal date: {r['date'].date()}"); print(f"BAC proxy spread: {r['BAC_proxy_spread_bp']:.2f} bp"); print(f"JPM proxy spread: {r['JPM_proxy_spread_bp']:.2f} bp"); print(f"BAC-JPM differential: {r['pair_spread_bp']:.2f} bp"); print(f"Lagged 252-observation z-score: {r['hist_z']:.2f}")
    else: print("Not enough aligned observations yet for a full 252-observation lagged z-score.")

if __name__ == "__main__": main()
