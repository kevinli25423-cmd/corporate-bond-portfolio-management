from __future__ import annotations

from pathlib import Path
import sys

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from corporate_bond_pm.data import load_project_data, latest_snapshot, point_in_time_fundamentals
from corporate_bond_pm.expected_return import expected_return_from_rv
from corporate_bond_pm.fundamentals import build_fundamental_scorecard
from corporate_bond_pm.relative_value import (
    fair_pair_differential,
    fit_cross_sectional_fair_oas,
    historical_pair_signal,
)
from corporate_bond_pm.risk import bond_cs01, bond_dv01
from corporate_bond_pm.stress import portfolio_stress

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


def _latest_rv_metrics(data) -> dict:
    cfg = data.config
    reps = _representative_map(data.security_master)
    bac_sec = reps["BAC"]
    jpm_sec = reps["JPM"]

    latest_market = latest_snapshot(data.market_daily)
    latest_cds = latest_snapshot(data.cds_daily).set_index("issuer")
    latest_liq = latest_snapshot(data.liquidity_daily).set_index("security_id")
    as_of = latest_market["date"].max()

    bac = latest_market.loc[latest_market["security_id"].eq(bac_sec)].iloc[0]
    jpm = latest_market.loc[latest_market["security_id"].eq(jpm_sec)].iloc[0]

    pair = historical_pair_signal(
        data.market_daily,
        bac_sec,
        jpm_sec,
        cfg["historical_window"],
        cfg["min_history"],
    )
    p = pair.iloc[-1]

    liquidity_adj = (
        latest_liq.loc[jpm_sec, "liquidity_score"]
        - latest_liq.loc[bac_sec, "liquidity_score"]
    ) * 8.0
    duration_adj = (bac["spread_duration"] - jpm["spread_duration"]) * 0.5
    fair = fair_pair_differential(
        bac["oas_bp"],
        jpm["oas_bp"],
        latest_cds.loc["BAC", "cds_5y_bp"],
        latest_cds.loc["JPM", "cds_5y_bp"],
        duration_adj_bp=duration_adj,
        liquidity_adj_bp=liquidity_adj,
    )

    reg_latest, _ = fit_cross_sectional_fair_oas(
        data.market_daily,
        data.cds_daily,
        data.liquidity_daily,
        data.security_master,
    )
    reg_map = reg_latest.set_index("security_id")["regression_rv_bp"]
    model_rv = float(reg_map.loc[bac_sec])
    hist_component = float(p["pair_spread_bp"] - p["hist_mean_bp"])
    blended_rv = (
        0.50 * fair["rv_residual_bp"]
        + 0.25 * hist_component
        + 0.25 * model_rv
    )

    exp = expected_return_from_rv(
        rv_bp=blended_rv,
        spread_duration=float(bac["spread_duration"]),
        carry_1m_bp=float(bac["carry_1m_bp"]),
        rolldown_1m_bp=float(bac["rolldown_1m_bp"]),
        transaction_cost_bp=cfg["transaction_cost_bp"],
        convergence_ratio=cfg["convergence_ratio"],
    )

    scorecard = build_fundamental_scorecard(
        point_in_time_fundamentals(data.fundamentals, as_of)
    ).set_index("issuer")

    trade_notional = 10_000_000.0
    bac_dv01 = bond_dv01(trade_notional, float(bac["modified_duration"]))
    jpm_dv01_per_dollar = bond_dv01(1.0, float(jpm["modified_duration"]))
    jpm_hedge_notional = bac_dv01 / jpm_dv01_per_dollar
    bac_cs01 = bond_cs01(trade_notional, float(bac["spread_duration"]))
    jpm_cs01 = bond_cs01(jpm_hedge_notional, float(jpm["spread_duration"]))

    return {
        "as_of": as_of,
        "bac_sec": bac_sec,
        "jpm_sec": jpm_sec,
        "bac": bac,
        "jpm": jpm,
        "pair": pair,
        "pair_latest": p,
        "fair": fair,
        "duration_adj_bp": duration_adj,
        "liquidity_adj_bp": liquidity_adj,
        "model_rv_bp": model_rv,
        "hist_component_bp": hist_component,
        "blended_rv_bp": blended_rv,
        "expected": exp,
        "latest_cds": latest_cds,
        "latest_liq": latest_liq,
        "scorecard": scorecard,
        "trade_notional": trade_notional,
        "jpm_hedge_notional": jpm_hedge_notional,
        "bac_dv01": bac_dv01,
        "jpm_dv01": bond_dv01(jpm_hedge_notional, float(jpm["modified_duration"])),
        "bac_cs01": bac_cs01,
        "jpm_cs01": jpm_cs01,
    }


def _build_stress_comparison(data, metrics: dict) -> pd.DataFrame:
    cfg = data.config
    latest = latest_snapshot(data.market_daily)
    reps = _representative_map(data.security_master)
    rows = []
    for asset in ["JPM", "BAC", "C", "WFC"]:
        sec = reps[asset]
        m = latest.loc[latest["security_id"].eq(sec)].iloc[0]
        rows.append({
            "asset": asset,
            "modified_duration": m["modified_duration"],
            "spread_duration": m["spread_duration"],
            "stress_spread_multiplier": cfg["stress_spread_multipliers"][asset],
            "stress_liquidity_multiplier": cfg["stress_liquidity_multipliers"][asset],
        })
    rows.append({
        "asset": "Cash",
        "modified_duration": 0.0,
        "spread_duration": 0.0,
        "stress_spread_multiplier": 0.0,
        "stress_liquidity_multiplier": 0.0,
    })
    risk = pd.DataFrame(rows)
    current_weights = data.holdings.set_index("asset")["weight"]
    current = risk.copy()
    current["weight"] = current["asset"].map(current_weights)

    proposed = current.copy()
    # +$10M BAC / -DV01-matched JPM within a $100M sleeve.
    add_bac = metrics["trade_notional"] / cfg["portfolio_market_value"]
    reduce_jpm = metrics["jpm_hedge_notional"] / cfg["portfolio_market_value"]
    proposed.loc[proposed["asset"].eq("BAC"), "weight"] += add_bac
    proposed.loc[proposed["asset"].eq("JPM"), "weight"] -= reduce_jpm
    # Small residual from DV01 matching is absorbed by cash to preserve sum(weights)=1.
    residual = 1.0 - proposed["weight"].sum()
    proposed.loc[proposed["asset"].eq("Cash"), "weight"] += residual

    frames = []
    for label, portfolio in [("Current", current), ("Proposed", proposed)]:
        s = portfolio_stress(portfolio, cfg["stress_scenarios"])
        s.insert(0, "portfolio", label)
        frames.append(s)
    return pd.concat(frames, ignore_index=True)


def _save_figures(data, metrics: dict, stress: pd.DataFrame) -> None:
    pair = metrics["pair"].copy()
    market = data.market_daily
    bac = market.loc[market["security_id"].eq(metrics["bac_sec"]), ["date", "oas_bp"]]
    jpm = market.loc[market["security_id"].eq(metrics["jpm_sec"]), ["date", "oas_bp"]]

    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.plot(bac["date"], bac["oas_bp"], label="BAC representative bond")
    ax.plot(jpm["date"], jpm["oas_bp"], label="JPM representative bond")
    ax.set_title("Synthetic BAC vs JPM OAS History")
    ax.set_ylabel("OAS (bp)")
    ax.set_xlabel("Date")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "bac_jpm_oas_history.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.plot(pair["date"], pair["pair_spread_bp"], label="BAC OAS - JPM OAS")
    ax.plot(pair["date"], pair["hist_mean_bp"], label="Lagged rolling mean")
    ax.set_title("BAC-JPM Pair Spread vs Lagged Historical Mean")
    ax.set_ylabel("Spread differential (bp)")
    ax.set_xlabel("Date")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "bac_jpm_pair_spread.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.plot(pair["date"], pair["hist_z"], label="Lagged rolling z-score")
    ax.axhline(1.0, linestyle="--", linewidth=1)
    ax.axhline(-1.0, linestyle="--", linewidth=1)
    ax.axhline(0.0, linewidth=1)
    ax.set_title("BAC-JPM Historical Relative-Value Z-Score")
    ax.set_ylabel("Z-score")
    ax.set_xlabel("Date")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "bac_jpm_zscore.png", dpi=160)
    plt.close(fig)

    labels = [
        "Market\ndifferential",
        "CDS credit\ndifferential",
        "Bond/liquidity\nadjustment",
        "Fair\ndifferential",
        "RV\nresidual",
    ]
    values = [
        metrics["fair"]["market_diff_bp"],
        metrics["fair"]["credit_diff_bp"],
        metrics["fair"]["bond_liquidity_adj_bp"],
        metrics["fair"]["fair_diff_bp"],
        metrics["fair"]["rv_residual_bp"],
    ]
    fig, ax = plt.subplots(figsize=(9, 5.2))
    ax.bar(labels, values)
    ax.axhline(0.0, linewidth=1)
    ax.set_title("Latest BAC-JPM Fair-Differential Decomposition")
    ax.set_ylabel("Basis points")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "bac_jpm_rv_decomposition.png", dpi=160)
    plt.close(fig)

    pivot = stress.pivot(index="scenario", columns="portfolio", values="portfolio_return_pct")
    pivot = pivot.reindex(["Normal", "Slowdown", "Crisis"])
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    x = range(len(pivot.index))
    width = 0.36
    ax.bar([i - width / 2 for i in x], pivot["Current"], width=width, label="Current")
    ax.bar([i + width / 2 for i in x], pivot["Proposed"], width=width, label="Proposed")
    ax.set_xticks(list(x), pivot.index)
    ax.set_title("Current vs Proposed Sleeve Stress Return")
    ax.set_ylabel("Portfolio return (%)")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "bac_jpm_stress_comparison.png", dpi=160)
    plt.close(fig)


def _write_case_study(data, metrics: dict, stress: pd.DataFrame) -> None:
    p = metrics["pair_latest"]
    fair = metrics["fair"]
    exp = metrics["expected"]
    score = metrics["scorecard"]
    latest_cds = metrics["latest_cds"]
    latest_liq = metrics["latest_liq"]
    cfg = data.config

    stress_pivot = stress.pivot(index="scenario", columns="portfolio", values="portfolio_return_pct")
    stress_pivot = stress_pivot.reindex(["Normal", "Slowdown", "Crisis"])

    decision = "Add BAC / Reduce JPM" if metrics["blended_rv_bp"] > 1.5 else "Hold"
    case = f"""# BAC vs JPM Relative-Value Case Study

> **Synthetic research example.** All bond-level OAS, CDS, liquidity, portfolio weights, expected returns, and stress results in this case study are generated from the repository's deterministic demo dataset. They are not live market quotations or investment recommendations.

## Research question

Does the additional spread on the representative Bank of America bond provide enough compensation relative to a closely matched JPMorgan bond after accounting for market-implied credit, bond/liquidity characteristics, historical relative value, expected convergence, risk, and stress?

**As of:** {metrics['as_of'].date()}  
**Representative securities:** `{metrics['bac_sec']}` vs `{metrics['jpm_sec']}`

## 1. Current market relationship

| Metric | BAC | JPM | BAC - JPM |
|---|---:|---:|---:|
| OAS | {metrics['bac']['oas_bp']:.2f} bp | {metrics['jpm']['oas_bp']:.2f} bp | {fair['market_diff_bp']:.2f} bp |
| 5Y CDS | {latest_cds.loc['BAC', 'cds_5y_bp']:.2f} bp | {latest_cds.loc['JPM', 'cds_5y_bp']:.2f} bp | {fair['credit_diff_bp']:.2f} bp |
| Spread duration | {metrics['bac']['spread_duration']:.2f} | {metrics['jpm']['spread_duration']:.2f} | {metrics['bac']['spread_duration'] - metrics['jpm']['spread_duration']:.2f} |
| Liquidity score | {latest_liq.loc[metrics['bac_sec'], 'liquidity_score']:.3f} | {latest_liq.loc[metrics['jpm_sec'], 'liquidity_score']:.3f} | {latest_liq.loc[metrics['bac_sec'], 'liquidity_score'] - latest_liq.loc[metrics['jpm_sec'], 'liquidity_score']:.3f} |
| Fundamental score | {score.loc['BAC', 'fundamental_score']:.2f} | {score.loc['JPM', 'fundamental_score']:.2f} | — |
| Credit view | {score.loc['BAC', 'credit_view']} | {score.loc['JPM', 'credit_view']} | — |

![Synthetic BAC and JPM OAS history](figures/bac_jpm_oas_history.png)

## 2. Historical relative value

The pair spread is defined as:

```text
D_t = OAS_BAC,t - OAS_JPM,t
```

The historical benchmark uses a lagged rolling mean and standard deviation so the current observation does not enter its own benchmark.

| Metric | Latest value |
|---|---:|
| BAC-JPM pair spread | {p['pair_spread_bp']:.2f} bp |
| Lagged rolling mean | {p['hist_mean_bp']:.2f} bp |
| Deviation from mean | {metrics['hist_component_bp']:.2f} bp |
| Historical z-score | {p['hist_z']:.2f}σ |

![Pair spread history](figures/bac_jpm_pair_spread.png)

![Historical z-score](figures/bac_jpm_zscore.png)

## 3. Fair differential and residual

The cash-bond differential is decomposed as:

```text
D_fair = CDS differential + duration adjustment + liquidity adjustment + structure adjustment
RV = D_market - D_fair
```

| Component | Value |
|---|---:|
| Observed market differential | {fair['market_diff_bp']:.2f} bp |
| CDS credit differential | {fair['credit_diff_bp']:.2f} bp |
| Duration adjustment | {metrics['duration_adj_bp']:.2f} bp |
| Liquidity adjustment | {metrics['liquidity_adj_bp']:.2f} bp |
| Fair differential | {fair['fair_diff_bp']:.2f} bp |
| CDS/bond RV residual | **{fair['rv_residual_bp']:.2f} bp** |
| Cross-sectional regression residual | {metrics['model_rv_bp']:.2f} bp |
| Historical deviation component | {metrics['hist_component_bp']:.2f} bp |
| **Blended RV signal** | **{metrics['blended_rv_bp']:.2f} bp** |

The blended signal uses the research weights in the pipeline: 50% CDS/bond residual, 25% historical deviation, and 25% cross-sectional regression residual.

![RV decomposition](figures/bac_jpm_rv_decomposition.png)

## 4. Expected return economics

Using the configured convergence assumption of {cfg['convergence_ratio']:.0%}:

| Component | Value |
|---|---:|
| Expected spread move | {exp['expected_spread_move_bp']:.2f} bp |
| Spread-convergence return | {exp['convergence_return_bp']:.2f} bp |
| 1M carry | {metrics['bac']['carry_1m_bp']:.2f} bp |
| 1M roll-down | {metrics['bac']['rolldown_1m_bp']:.2f} bp |
| Transaction cost | -{cfg['transaction_cost_bp']:.2f} bp |
| **Expected 1M return** | **{exp['expected_return_1m_bp']:.2f} bp** |

The convergence assumption is a forecast parameter rather than a fact. The separate backtest module tests whether historical synthetic signals subsequently converged and reports realized convergence ratios.

## 5. Trade sizing and risk

Illustrative trade:

```text
BUY $10.0M BAC
REDUCE approximately ${metrics['jpm_hedge_notional'] / 1_000_000:.2f}M JPM
```

The JPM reduction is sized from DV01 so the rates exposure of the pair is approximately neutral.

| Risk measure | BAC leg | JPM hedge leg |
|---|---:|---:|
| DV01 | ${metrics['bac_dv01']:,.0f}/bp | ${metrics['jpm_dv01']:,.0f}/bp |
| CS01 | ${metrics['bac_cs01']:,.0f}/bp | ${metrics['jpm_cs01']:,.0f}/bp |

The trade intentionally shifts issuer spread exposure toward BAC while keeping the Treasury-duration effect approximately matched.

## 6. Stress overlay

| Scenario | Current sleeve | Proposed sleeve | Change |
|---|---:|---:|---:|
| Normal | {stress_pivot.loc['Normal', 'Current']:.2f}% | {stress_pivot.loc['Normal', 'Proposed']:.2f}% | {stress_pivot.loc['Normal', 'Proposed'] - stress_pivot.loc['Normal', 'Current']:+.2f}% |
| Slowdown | {stress_pivot.loc['Slowdown', 'Current']:.2f}% | {stress_pivot.loc['Slowdown', 'Proposed']:.2f}% | {stress_pivot.loc['Slowdown', 'Proposed'] - stress_pivot.loc['Slowdown', 'Current']:+.2f}% |
| Crisis | {stress_pivot.loc['Crisis', 'Current']:.2f}% | {stress_pivot.loc['Crisis', 'Proposed']:.2f}% | {stress_pivot.loc['Crisis', 'Proposed'] - stress_pivot.loc['Crisis', 'Current']:+.2f}% |

![Stress comparison](figures/bac_jpm_stress_comparison.png)

## 7. Research conclusion

**Model action: {decision}.**

The synthetic example shows BAC trading materially wider than JPM relative to the lagged historical relationship. CDS, bond characteristics, and liquidity explain part—but not all—of the observed differential. The blended relative-value signal remains positive, and the expected-return calculation compensates for transaction cost.

The position is therefore implemented as a **moderate BAC overweight versus JPM rather than an unconstrained allocation**. The trade is DV01-matched, issuer CS01 is monitored explicitly, and the stress comparison shows the incremental downside cost of shifting toward the higher-spread issuer.

The objective is not to label BAC as universally "cheap." It is to show a reproducible process for asking whether the incremental spread is sufficient compensation for the incremental credit, liquidity, concentration, and tail risk in the synthetic research environment.
"""
    (ROOT / "docs" / "bac_jpm_case_study.md").write_text(case, encoding="utf-8")

    summary = pd.DataFrame([{
        "as_of": metrics["as_of"].date(),
        "bac_security": metrics["bac_sec"],
        "jpm_security": metrics["jpm_sec"],
        "bac_oas_bp": metrics["bac"]["oas_bp"],
        "jpm_oas_bp": metrics["jpm"]["oas_bp"],
        "market_diff_bp": fair["market_diff_bp"],
        "historical_mean_diff_bp": p["hist_mean_bp"],
        "historical_z": p["hist_z"],
        "cds_diff_bp": fair["credit_diff_bp"],
        "fair_diff_bp": fair["fair_diff_bp"],
        "cds_bond_rv_bp": fair["rv_residual_bp"],
        "regression_rv_bp": metrics["model_rv_bp"],
        "blended_rv_bp": metrics["blended_rv_bp"],
        "expected_return_1m_bp": exp["expected_return_1m_bp"],
        "model_action": decision,
    }])
    summary.to_csv(RESULT_DIR / "bac_jpm_case_summary.csv", index=False)
    stress.to_csv(RESULT_DIR / "bac_jpm_stress_comparison.csv", index=False)


def main() -> None:
    data = load_project_data(ROOT)
    metrics = _latest_rv_metrics(data)
    stress = _build_stress_comparison(data, metrics)
    _save_figures(data, metrics, stress)
    _write_case_study(data, metrics, stress)
    print("BAC/JPM case study complete")
    print(f"Case study: {ROOT / 'docs' / 'bac_jpm_case_study.md'}")
    print(f"Figures: {FIG_DIR}")


if __name__ == "__main__":
    main()
