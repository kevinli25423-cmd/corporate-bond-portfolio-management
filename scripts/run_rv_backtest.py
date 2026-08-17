from __future__ import annotations

from pathlib import Path
import sys

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from corporate_bond_pm.data import load_project_data
from corporate_bond_pm.validation import (
    PairBacktestConfig,
    build_pair_validation_panel,
    independent_event_backtest,
    summarize_signal_days,
)

FIG_DIR = ROOT / "docs" / "figures"
RESULT_DIR = ROOT / "docs" / "results"
FIG_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)


def _representative_map(security_master: pd.DataFrame) -> dict[str, str]:
    return (
        security_master.loc[security_master["representative"]]
        .set_index("issuer")["security_id"]
        .to_dict()
    )


def _save_figures(
    panel: pd.DataFrame,
    signal_summary: pd.DataFrame,
    events: pd.DataFrame,
) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    ax.bar(
        signal_summary["horizon_days"].astype(str) + "D",
        signal_summary["avg_signed_convergence_bp"],
    )
    ax.axhline(0.0, linewidth=1)
    ax.set_title("Average Signed Pair Convergence After |Z| ≥ 1")
    ax.set_ylabel("Average convergence (bp)")
    ax.set_xlabel("Forward horizon")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "bac_jpm_backtest_horizon_summary.png", dpi=160)
    plt.close(fig)

    x = panel.loc[panel["hist_z"].abs() >= 1.0].dropna(
        subset=["signed_convergence_20d_bp"]
    )
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    ax.scatter(x["hist_z"].abs(), x["signed_convergence_20d_bp"], alpha=0.75)
    ax.axhline(0.0, linewidth=1)
    ax.set_title("Signal Strength vs 20D Subsequent Pair Convergence")
    ax.set_xlabel("Absolute lagged historical z-score")
    ax.set_ylabel("Signed 20D convergence (bp)")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "bac_jpm_signal_vs_20d_convergence.png", dpi=160)
    plt.close(fig)

    if not events.empty:
        fig, ax = plt.subplots(figsize=(10, 5.4))
        labels = events["date"].dt.strftime("%Y-%m-%d")
        positions = list(range(len(events)))
        width = 0.36
        ax.bar(
            [i - width / 2 for i in positions],
            events["gross_pair_return_bp"],
            width=width,
            label="Gross",
        )
        ax.bar(
            [i + width / 2 for i in positions],
            events["net_pair_return_bp"],
            width=width,
            label="After assumed pair cost",
        )
        ax.axhline(0.0, linewidth=1)
        ax.set_xticks(positions, labels, rotation=45, ha="right")
        ax.set_title("Independent 20D Threshold-Crossing Events")
        ax.set_ylabel("Approximate pair return (bp)")
        ax.legend()
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(FIG_DIR / "bac_jpm_event_returns_20d.png", dpi=160)
        plt.close(fig)


def _write_backtest_doc(
    cfg: PairBacktestConfig,
    signal_summary: pd.DataFrame,
    events: pd.DataFrame,
    event_summary: pd.DataFrame,
) -> None:
    s20 = signal_summary.loc[signal_summary["horizon_days"].eq(20)].iloc[0]
    e = event_summary.iloc[0]

    signal_rows = "\n".join(
        f"| {int(r.horizon_days)}D | {int(r.observations)} | {r.avg_signed_convergence_bp:.2f} bp | "
        f"{r.convergence_hit_rate:.1%} | {r.avg_gross_pair_return_bp:.2f} bp | "
        f"{r.avg_clipped_convergence_ratio:.2f} |"
        for r in signal_summary.itertuples()
    )

    event_rows = "\n".join(
        f"| {r.date.date()} | {r.hist_z:.2f} | {'Long BAC / Short JPM' if r.hist_z > 0 else 'Short BAC / Long JPM'} | "
        f"{getattr(r, 'signed_convergence_20d_bp'):.2f} bp | {r.gross_pair_return_bp:.2f} bp | {r.net_pair_return_bp:.2f} bp |"
        for r in events.itertuples()
    )

    doc = f"""# BAC vs JPM Relative-Value Signal Validation

> **Synthetic research backtest.** The results below use the deterministic demo data included in this repository. They demonstrate a chronological validation design; they are not evidence about live BAC or JPM bonds and should not be interpreted as an investable historical track record.

## Objective

Test whether historical BAC-JPM relative-value dislocations tend to mean-revert after the signal is formed.

The signal uses only information available at time `t`:

```text
D_t = OAS_BAC,t - OAS_JPM,t
Z_t = (D_t - lagged rolling mean) / lagged rolling standard deviation
```

The rolling mean and standard deviation are lagged by one day. Future pair changes are added only after the signal has been computed, so the validation does not use future information to form `Z_t`.

## 1. Daily signal validation

Signal condition:

```text
|Z_t| >= {cfg.signal_threshold:.1f}
```

A positive signed convergence means the pair subsequently moved in the direction predicted by mean reversion. Consecutive signal days can overlap, so these observations are useful for signal diagnostics but are **not independent trades**.

| Horizon | Signal-day observations | Avg signed convergence | Convergence hit rate | Avg gross pair return | Avg clipped realized q |
|---|---:|---:|---:|---:|---:|
{signal_rows}

For the 20-business-day horizon, the synthetic sample shows an average signed convergence of **{s20['avg_signed_convergence_bp']:.2f} bp** with a **{s20['convergence_hit_rate']:.1%}** convergence hit rate. The average clipped realized convergence ratio is **{s20['avg_clipped_convergence_ratio']:.2f}**.

![Average convergence by horizon](figures/bac_jpm_backtest_horizon_summary.png)

![Signal strength vs future convergence](figures/bac_jpm_signal_vs_20d_convergence.png)

## 2. Independent event backtest

To reduce overlap, a trade event starts only when `|Z|` crosses the threshold from below. No new event is permitted until the {cfg.event_horizon}-business-day holding period has elapsed.

The approximate pair return uses matched spread duration:

```text
Gross pair return (bp) ≈ matched spread duration × signed pair convergence (bp)
```

The net result subtracts an explicit **{cfg.pair_transaction_cost_bp:.1f} bp all-in pair implementation-cost assumption**. This is a research assumption, not an observed historical execution cost.

| Entry date | Entry Z | Direction | 20D convergence | Gross return | Net return |
|---|---:|---|---:|---:|---:|
{event_rows}

### Independent-event summary

| Metric | Result |
|---|---:|
| Number of events | {int(e['events'])} |
| Average signed convergence | {e['avg_signed_convergence_bp']:.2f} bp |
| Gross convergence hit rate | {e['gross_hit_rate']:.1%} |
| Average gross pair return | {e['avg_gross_pair_return_bp']:.2f} bp |
| Average net pair return | {e['avg_net_pair_return_bp']:.2f} bp |
| Net-positive event rate | {e['net_positive_rate']:.1%} |
| Avg clipped realized convergence ratio | {e['avg_clipped_convergence_ratio']:.2f} |

![Independent event returns](figures/bac_jpm_event_returns_20d.png)

## 3. How this informs the expected-return model

The portfolio code contains a convergence parameter `q` in:

```text
E[ΔSpread] = -q × RV
```

The backtest provides an empirical way to challenge that assumption. In this synthetic sample, the 20D daily-signal average clipped realized convergence ratio is **{s20['avg_clipped_convergence_ratio']:.2f}**, while the independent-event average clipped ratio is **{e['avg_clipped_convergence_ratio']:.2f}**.

This does **not** prove a stable real-world value for `q`. It demonstrates the correct validation workflow: estimate the parameter from chronologically subsequent outcomes, compare it with the model assumption, and re-estimate as the sample grows.

## 4. Limitations

- The dataset is synthetic and deliberately contains structured mean reversion.
- Consecutive daily signal observations are serially correlated.
- The independent-event sample is small.
- Spread-duration approximation ignores convexity and detailed carry/financing of a true long-short implementation.
- Transaction cost is an explicit assumption rather than historical executable quotes.
- A production study would repeat the analysis across many matched issuer/bond pairs and use walk-forward model estimation.

The purpose of this module is therefore **methodological validation**, not a claim of historical alpha in live bonds.
"""
    (ROOT / "docs" / "bac_jpm_backtest.md").write_text(doc, encoding="utf-8")


def main() -> None:
    data = load_project_data(ROOT)
    reps = _representative_map(data.security_master)
    cfg = PairBacktestConfig(
        window=int(data.config["historical_window"]),
        min_history=int(data.config["min_history"]),
        signal_threshold=1.0,
        horizons=(5, 20, 60),
        event_horizon=20,
        pair_transaction_cost_bp=2.0 * float(data.config["transaction_cost_bp"]),
    )

    panel = build_pair_validation_panel(
        data.market_daily,
        reps["BAC"],
        reps["JPM"],
        window=cfg.window,
        min_history=cfg.min_history,
        horizons=cfg.horizons,
    )
    signal_summary = summarize_signal_days(
        panel,
        signal_threshold=cfg.signal_threshold,
        horizons=cfg.horizons,
    )
    events, event_summary = independent_event_backtest(
        panel,
        signal_threshold=cfg.signal_threshold,
        horizon_days=cfg.event_horizon,
        pair_transaction_cost_bp=cfg.pair_transaction_cost_bp,
    )

    panel.to_csv(RESULT_DIR / "bac_jpm_validation_panel.csv", index=False)
    signal_summary.to_csv(RESULT_DIR / "bac_jpm_signal_summary.csv", index=False)
    events.to_csv(RESULT_DIR / "bac_jpm_event_backtest.csv", index=False)
    event_summary.to_csv(RESULT_DIR / "bac_jpm_event_summary.csv", index=False)

    _save_figures(panel, signal_summary, events)
    _write_backtest_doc(cfg, signal_summary, events, event_summary)

    print("BAC/JPM RV validation complete")
    print("\nDaily signal summary:")
    print(signal_summary.round(4).to_string(index=False))
    print("\nIndependent-event summary:")
    print(event_summary.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
