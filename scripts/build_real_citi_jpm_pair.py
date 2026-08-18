from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from corporate_bond_pm.bond_math import FixedToFloatBond, yield_to_call_from_clean_price
from corporate_bond_pm.real_pair import (
    add_forward_validation,
    add_lagged_zscore,
    assess_validation,
    classify_signal,
    independent_event_backtest,
    modified_duration_to_call,
    summarize_signal_days,
)
from corporate_bond_pm.trace_real import daily_trade_summary, load_finra_trade_export
from corporate_bond_pm.treasury_real import attach_treasury_proxy, fetch_treasury_yield_curve_range

CONFIG = ROOT / "config" / "real_citi_jpm_pair.json"
OUT_DIR = ROOT / "data" / "processed" / "real"
RESULT_DIR = ROOT / "docs" / "results" / "real"
FIG_DIR = ROOT / "docs" / "figures"


def build_security_daily(path: Path, terms: dict, representative: str, args) -> pd.DataFrame:
    trades = load_finra_trade_export(path, date_col=args.date_col, price_col=args.price_col, volume_col=args.volume_col)
    daily = daily_trade_summary(trades, representative=representative)
    bond = FixedToFloatBond.from_dict(terms)
    daily = daily.loc[daily["date"] < pd.Timestamp(bond.first_par_call_date)].copy()
    ytc = [yield_to_call_from_clean_price(bond, d.date(), p) for d, p in zip(daily["date"], daily["representative_price"])]
    daily["ytc_pct"] = 100.0 * np.asarray(ytc)
    daily["duration_to_call"] = [
        modified_duration_to_call(bond, d.date(), y)
        for d, y in zip(daily["date"], ytc)
    ]
    daily["issuer"] = terms["issuer"]
    daily["cusip"] = terms["cusip"]
    return daily


def save_figures(pair: pd.DataFrame) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 5.4))
    ax.plot(pair["date"], pair["CITI_treasury_spread_bp"], label="CITI YTC−Treasury spread")
    ax.plot(pair["date"], pair["JPM_treasury_spread_bp"], label="JPM YTC−Treasury spread")
    ax.set_title("Real CITI / JPM YTC−Treasury Spreads")
    ax.set_ylabel("Basis points")
    ax.legend(); ax.grid(alpha=0.25); fig.tight_layout()
    fig.savefig(FIG_DIR / "real_citi_jpm_treasury_spreads.png", dpi=170); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5.4))
    ax.plot(pair["date"], pair["pair_spread_bp"], label="CITI − JPM")
    if pair["hist_mean_bp"].notna().any():
        ax.plot(pair["date"], pair["hist_mean_bp"], label="Lagged 252-observation mean")
        upper = pair["hist_mean_bp"] + 2.0 * pair["hist_std_bp"]
        lower = pair["hist_mean_bp"] - 2.0 * pair["hist_std_bp"]
        ax.plot(pair["date"], upper, linestyle="--", linewidth=1, label="±2σ band")
        ax.plot(pair["date"], lower, linestyle="--", linewidth=1)
    ax.axhline(0.0, linewidth=1)
    ax.set_title("Real CITI − JPM Treasury-Spread Differential")
    ax.set_ylabel("Basis points")
    ax.legend(); ax.grid(alpha=0.25); fig.tight_layout()
    fig.savefig(FIG_DIR / "real_citi_jpm_pair_spread.png", dpi=170); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5.4))
    ax.plot(pair["date"], pair["hist_z"])
    ax.axhline(0.0, linewidth=1)
    ax.axhline(1.0, linestyle="--", linewidth=1); ax.axhline(-1.0, linestyle="--", linewidth=1)
    ax.axhline(2.0, linestyle=":", linewidth=1); ax.axhline(-2.0, linestyle=":", linewidth=1)
    ax.set_title("Real CITI − JPM Lagged Historical Z-Score")
    ax.set_ylabel("Z-score")
    ax.grid(alpha=0.25); fig.tight_layout()
    fig.savefig(FIG_DIR / "real_citi_jpm_zscore.png", dpi=170); plt.close(fig)


def write_summary(pair: pd.DataFrame, signal_summary: pd.DataFrame, event_summary: pd.DataFrame, cfg: dict) -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    valid = pair.dropna(subset=["hist_z"])
    validation_status, pm_decision, validation_reason = assess_validation(
        signal_summary,
        event_summary,
        primary_horizon=int(cfg.get("validation_primary_horizon", 20)),
        min_independent_events=int(cfg.get("min_independent_events", 5)),
    )

    if valid.empty:
        latest = None
        latest_text = "A full lagged 252-observation signal is not yet available."
    else:
        latest = valid.iloc[-1]
        signal, direction = classify_signal(
            latest["hist_z"],
            threshold=float(cfg["signal_threshold_abs_z"]),
            strong_threshold=float(cfg["strong_signal_threshold_abs_z"]),
        )
        latest_text = (
            f"Latest fully formed signal date: **{latest['date'].date()}**. "
            f"CITI YTC−Treasury spread: **{latest['CITI_treasury_spread_bp']:.2f} bp**; "
            f"JPM YTC−Treasury spread: **{latest['JPM_treasury_spread_bp']:.2f} bp**; "
            f"CITI−JPM differential: **{latest['pair_spread_bp']:.2f} bp**; "
            f"lagged z-score: **{latest['hist_z']:.2f}σ**; "
            f"raw signal: **{signal}**; mean-reversion direction: **{direction}**. "
            f"Historical validation: **{validation_status}**. PM decision: **{pm_decision}**."
        )

    rows = []
    for _, r in signal_summary.iterrows():
        rows.append(
            f"| {int(r['horizon_observations'])} obs | {int(r['observations'])} | "
            f"{r['avg_signed_convergence_bp']:.2f} bp | {r['convergence_hit_rate']:.1%} | "
            f"{r['avg_gross_pair_return_bp']:.2f} bp |"
        )

    erows = []
    for _, r in event_summary.iterrows():
        erows.append(
            f"| {int(r['horizon_observations'])} obs | {int(r['events'])} | "
            f"{r.get('gross_hit_rate', np.nan):.1%} | {r.get('avg_gross_pair_return_bp', np.nan):.2f} bp | "
            f"{r.get('avg_net_pair_return_bp', np.nan):.2f} bp | {r.get('net_positive_rate', np.nan):.1%} |"
        )

    md = f'''# V2 — Real CITI/JPM Relative-Value Pair

This module uses locally stored FINRA public fixed-income observations for CITI **172967ME8** and JPM **46647PBE5**, combined with official U.S. Treasury daily par yields.

## Latest result

{latest_text}

**Validation gate:** {validation_reason}

![Real CITI/JPM YTC-Treasury spreads](../../figures/real_citi_jpm_treasury_spreads.png)

![Real CITI/JPM pair spread](../../figures/real_citi_jpm_pair_spread.png)

![Real CITI/JPM lagged z-score](../../figures/real_citi_jpm_zscore.png)

## Signal-day chronological validation

Positive signed convergence means the future pair move was in the direction implied by the contemporaneous mean-reversion signal. These rows are signal observations and can overlap.

| Horizon | Signal obs (`|Z|>=1`) | Avg convergence | Hit rate | Avg duration-scaled gross return |
|---|---:|---:|---:|---:|
{chr(10).join(rows)}

## Independent event backtest

An event begins only when `|Z|` crosses the threshold from below, and no new event is admitted until the holding horizon has elapsed.

| Horizon | Events | Gross hit rate | Avg gross return | Avg net return | Net-positive rate |
|---|---:|---:|---:|---:|---:|
{chr(10).join(erows)}

Transaction-cost assumption: **{float(cfg['pair_transaction_cost_bp']):.1f} bp of pair return** per completed event.

## Spread definition

`YTC−Treasury spread = yield to first par call − Treasury par yield interpolated to the first par-call date`.

This is a transparent market spread measure for the public-data implementation. It is **not OAS** because the embedded call option is not separately valued with an option model.

## Decision framework

- The z-score creates a **raw statistical signal**, not an automatic trade.
- Positive `CITI − JPM` z-score implies a mean-reversion direction of **Long CITI / Short JPM**; negative z-score implies **Short CITI / Long JPM**.
- Historical signal-day and independent-event results are then used as a validation gate.
- A signal can therefore be statistically unusual while the final PM decision remains **No trade**.
'''
    (RESULT_DIR / "real_citi_jpm.md").write_text(md, encoding="utf-8")

    if latest is not None:
        signal, direction = classify_signal(
            latest["hist_z"],
            threshold=float(cfg["signal_threshold_abs_z"]),
            strong_threshold=float(cfg["strong_signal_threshold_abs_z"]),
        )
        pd.DataFrame([{
            "as_of": latest["date"].date().isoformat(),
            "citi_ytc_pct": latest["CITI_ytc_pct"],
            "citi_treasury_yield_pct": latest["CITI_treasury_yield_pct"],
            "citi_treasury_spread_bp": latest["CITI_treasury_spread_bp"],
            "jpm_ytc_pct": latest["JPM_ytc_pct"],
            "jpm_treasury_yield_pct": latest["JPM_treasury_yield_pct"],
            "jpm_treasury_spread_bp": latest["JPM_treasury_spread_bp"],
            "pair_spread_bp": latest["pair_spread_bp"],
            "hist_mean_bp": latest["hist_mean_bp"],
            "hist_std_bp": latest["hist_std_bp"],
            "hist_z": latest["hist_z"],
            "raw_signal": signal,
            "mean_reversion_direction": direction,
            "validation_status": validation_status,
            "pm_decision": pm_decision,
            "validation_reason": validation_reason,
            "aligned_observations": len(pair),
        }]).to_csv(RESULT_DIR / "citi_jpm_latest.csv", index=False)
    signal_summary.to_csv(RESULT_DIR / "citi_jpm_signal_summary.csv", index=False)
    event_summary.to_csv(RESULT_DIR / "citi_jpm_event_summary.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build real CITI/JPM relative-value pair")
    parser.add_argument("--citi", type=Path, default=ROOT / "data/raw/trace/CITI_172967ME8.csv")
    parser.add_argument("--jpm", type=Path, default=ROOT / "data/raw/trace/JPM_46647PBE5.csv")
    parser.add_argument("--date-col", default=None)
    parser.add_argument("--price-col", default=None)
    parser.add_argument("--volume-col", default=None)
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text())
    missing = [p for p in [args.citi, args.jpm] if not p.exists()]
    if missing:
        raise SystemExit(
            "Missing local FINRA CSV file(s):\n  " + "\n  ".join(str(p) for p in missing)
            + "\nRaw FINRA data is intentionally local-only and ignored by git."
        )

    representative = cfg.get("price_method", "median")
    citi = build_security_daily(args.citi, cfg["securities"]["CITI"], representative, args)
    jpm = build_security_daily(args.jpm, cfg["securities"]["JPM"], representative, args)

    treasury = fetch_treasury_yield_curve_range(
        min(citi["date"].min(), jpm["date"].min()),
        max(citi["date"].max(), jpm["date"].max()),
    )
    citi = attach_treasury_proxy(citi, treasury, call_date=cfg["securities"]["CITI"]["first_par_call_date"])
    jpm = attach_treasury_proxy(jpm, treasury, call_date=cfg["securities"]["JPM"]["first_par_call_date"])
    citi["treasury_spread_bp"] = (citi["ytc_pct"] - citi["treasury_yield_pct"]) * 100.0
    jpm["treasury_spread_bp"] = (jpm["ytc_pct"] - jpm["treasury_yield_pct"]) * 100.0

    cols = ["date", "representative_price", "trade_count", "displayed_volume", "ytc_pct", "duration_to_call", "treasury_yield_pct", "treasury_spread_bp"]
    c = citi[cols].rename(columns={k: f"CITI_{k}" for k in cols if k != "date"})
    j = jpm[cols].rename(columns={k: f"JPM_{k}" for k in cols if k != "date"})
    pair = c.merge(j, on="date", how="inner").sort_values("date").reset_index(drop=True)
    pair["pair_spread_bp"] = pair["CITI_treasury_spread_bp"] - pair["JPM_treasury_spread_bp"]
    pair["matched_duration"] = pair[["CITI_duration_to_call", "JPM_duration_to_call"]].mean(axis=1)
    pair = add_lagged_zscore(pair, window=int(cfg["historical_window"]))
    pair = add_forward_validation(pair, cfg["forward_horizons"])

    signal_summary = summarize_signal_days(
        pair,
        signal_threshold=float(cfg["signal_threshold_abs_z"]),
        horizons=cfg["forward_horizons"],
    )
    event_summaries = []
    event_frames = []
    for h in cfg["forward_horizons"]:
        events, summary = independent_event_backtest(
            pair,
            signal_threshold=float(cfg["signal_threshold_abs_z"]),
            horizon_observations=int(h),
            pair_transaction_cost_bp=float(cfg["pair_transaction_cost_bp"]),
        )
        if not events.empty:
            events.insert(0, "horizon_observations", int(h))
            event_frames.append(events)
        event_summaries.append(summary)
    event_summary = pd.concat(event_summaries, ignore_index=True)
    all_events = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pair.to_csv(OUT_DIR / "citi_jpm_real_pair_daily.csv", index=False)
    citi.to_csv(OUT_DIR / "citi_172967me8_daily.csv", index=False)
    jpm.to_csv(OUT_DIR / "jpm_46647pbe5_daily.csv", index=False)
    treasury.to_csv(OUT_DIR / "treasury_curve_daily.csv", index=False)
    if not all_events.empty:
        all_events.to_csv(OUT_DIR / "citi_jpm_backtest_events.csv", index=False)

    save_figures(pair)
    write_summary(pair, signal_summary, event_summary, cfg)

    print("V2 real CITI/JPM pair complete")
    print(f"Aligned pair observations: {len(pair)}")
    valid = pair.dropna(subset=["hist_z"])
    if valid.empty:
        print("Not enough aligned observations for a full lagged 252-observation z-score.")
        return
    r = valid.iloc[-1]
    signal, direction = classify_signal(
        r["hist_z"],
        threshold=float(cfg["signal_threshold_abs_z"]),
        strong_threshold=float(cfg["strong_signal_threshold_abs_z"]),
    )
    validation_status, pm_decision, validation_reason = assess_validation(
        signal_summary,
        event_summary,
        primary_horizon=int(cfg.get("validation_primary_horizon", 20)),
        min_independent_events=int(cfg.get("min_independent_events", 5)),
    )
    print(f"Latest signal date: {r['date'].date()}")
    print(f"CITI YTC: {r['CITI_ytc_pct']:.4f}%")
    print(f"CITI Treasury yield: {r['CITI_treasury_yield_pct']:.4f}%")
    print(f"CITI YTC-Treasury spread: {r['CITI_treasury_spread_bp']:.2f} bp")
    print(f"JPM YTC: {r['JPM_ytc_pct']:.4f}%")
    print(f"JPM Treasury yield: {r['JPM_treasury_yield_pct']:.4f}%")
    print(f"JPM YTC-Treasury spread: {r['JPM_treasury_spread_bp']:.2f} bp")
    print(f"CITI-JPM differential: {r['pair_spread_bp']:.2f} bp")
    print(f"Lagged {int(cfg['historical_window'])}-observation z-score: {r['hist_z']:.2f}")
    print(f"Raw signal: {signal}")
    print(f"Mean-reversion direction: {direction}")
    print(f"Historical validation: {validation_status}")
    print(f"PM decision: {pm_decision}")
    print(f"Reason: {validation_reason}")
    print("\nSignal-day backtest")
    print(signal_summary.to_string(index=False))
    print("\nIndependent-event backtest")
    print(event_summary.to_string(index=False))


if __name__ == "__main__":
    main()
