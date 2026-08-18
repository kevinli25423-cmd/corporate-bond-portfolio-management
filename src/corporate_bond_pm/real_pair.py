from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import numpy as np
import pandas as pd

from .bond_math import FixedToFloatBond, dirty_price_from_ytc


@dataclass(frozen=True)
class RealPairBacktestConfig:
    window: int = 252
    signal_threshold: float = 1.0
    strong_signal_threshold: float = 2.0
    horizons: tuple[int, ...] = (5, 20, 60)
    pair_transaction_cost_bp: float = 8.0


def modified_duration_to_call(
    bond: FixedToFloatBond,
    settlement: date | str,
    ytc_decimal: float,
    *,
    bump: float = 1e-4,
) -> float:
    """Numerical modified duration of fixed-rate cash flows to first par call."""
    p0 = dirty_price_from_ytc(bond, settlement, ytc_decimal)
    p_up = dirty_price_from_ytc(bond, settlement, ytc_decimal + bump)
    p_dn = dirty_price_from_ytc(bond, settlement, ytc_decimal - bump)
    if not np.isfinite(p0) or p0 <= 0:
        return np.nan
    return float(-(p_up - p_dn) / (2.0 * bump * p0))


def add_lagged_zscore(pair: pd.DataFrame, *, window: int = 252) -> pd.DataFrame:
    """Lag the historical distribution by one observation to avoid look-ahead."""
    x = pair.copy()
    lagged = x["pair_spread_bp"].shift(1)
    x["hist_mean_bp"] = lagged.rolling(window, min_periods=window).mean()
    x["hist_std_bp"] = lagged.rolling(window, min_periods=window).std(ddof=1)
    x["hist_z"] = (x["pair_spread_bp"] - x["hist_mean_bp"]) / x["hist_std_bp"]
    return x


def add_forward_validation(pair: pd.DataFrame, horizons: Iterable[int] = (5, 20, 60)) -> pd.DataFrame:
    """Append future-only outcomes after the lagged signal has been formed.

    Positive pair spread means CITI is wider than JPM. Positive z therefore implies
    long CITI / short JPM under a mean-reversion view. Signed convergence is positive
    when the pair subsequently moves in the direction implied by the signal.
    """
    x = pair.copy()
    direction = np.sign(x["hist_z"])
    if "matched_duration" not in x:
        duration_cols = [c for c in ["CITI_duration_to_call", "JPM_duration_to_call"] if c in x]
        x["matched_duration"] = x[duration_cols].mean(axis=1) if duration_cols else np.nan

    x["deviation_from_mean_bp"] = x["pair_spread_bp"] - x["hist_mean_bp"]
    for h in horizons:
        future_change = x["pair_spread_bp"].shift(-h) - x["pair_spread_bp"]
        signed_convergence = -direction * future_change
        x[f"future_pair_change_{h}obs_bp"] = future_change
        x[f"signed_convergence_{h}obs_bp"] = signed_convergence
        x[f"gross_pair_return_{h}obs_bp"] = x["matched_duration"] * signed_convergence
        denom = x["deviation_from_mean_bp"].abs().replace(0.0, np.nan)
        x[f"realized_convergence_ratio_{h}obs"] = signed_convergence / denom
    return x


def classify_signal(z: float, *, threshold: float = 1.0, strong_threshold: float = 2.0) -> tuple[str, str]:
    """Classify the raw statistical signal and its mean-reversion direction.

    This does *not* make the portfolio decision. Historical validation is applied
    separately so a statistical dislocation can still result in No Trade.
    """
    if z is None or not np.isfinite(z):
        return "Insufficient history", "No trade"
    a = abs(float(z))
    if a < threshold:
        return "Neutral", "No trade"
    if z > 0:
        trade = "Long CITI / Short JPM"
    else:
        trade = "Short CITI / Long JPM"
    if a >= strong_threshold:
        return "Strong RV", trade
    return "Watch / Moderate RV", trade


def summarize_signal_days(
    panel: pd.DataFrame,
    *,
    signal_threshold: float = 1.0,
    horizons: Iterable[int] = (5, 20, 60),
) -> pd.DataFrame:
    rows: list[dict] = []
    for h in horizons:
        conv = f"signed_convergence_{h}obs_bp"
        ret = f"gross_pair_return_{h}obs_bp"
        ratio = f"realized_convergence_ratio_{h}obs"
        x = panel.loc[panel["hist_z"].abs() >= signal_threshold].dropna(subset=[conv, ret])
        rows.append({
            "horizon_observations": h,
            "signal_threshold_abs_z": signal_threshold,
            "observations": int(len(x)),
            "avg_signed_convergence_bp": x[conv].mean(),
            "median_signed_convergence_bp": x[conv].median(),
            "convergence_hit_rate": (x[conv] > 0).mean(),
            "avg_gross_pair_return_bp": x[ret].mean(),
            "median_gross_pair_return_bp": x[ret].median(),
            "avg_realized_convergence_ratio": x[ratio].mean(),
            "avg_clipped_convergence_ratio": x[ratio].clip(0.0, 1.0).mean(),
        })
    return pd.DataFrame(rows)


def independent_event_backtest(
    panel: pd.DataFrame,
    *,
    signal_threshold: float = 1.0,
    horizon_observations: int = 20,
    pair_transaction_cost_bp: float = 8.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Threshold-crossing, non-overlapping event backtest.

    Transaction cost is expressed as basis points of pair return and subtracted
    once from the duration-scaled gross return estimate.
    """
    h = int(horizon_observations)
    conv = f"signed_convergence_{h}obs_bp"
    ret = f"gross_pair_return_{h}obs_bp"
    future = f"future_pair_change_{h}obs_bp"
    ratio = f"realized_convergence_ratio_{h}obs"

    full = panel.reset_index(drop=True).copy()
    valid = full.dropna(subset=["hist_z", conv, ret, future]).copy()
    entries: list[int] = []
    blocked_through = -1
    for idx in valid.index:
        if idx <= blocked_through:
            continue
        prev_z = full.loc[idx - 1, "hist_z"] if idx > 0 else np.nan
        prev_abs = abs(float(prev_z)) if pd.notna(prev_z) else 0.0
        z = float(full.loc[idx, "hist_z"])
        if abs(z) >= signal_threshold and prev_abs < signal_threshold:
            entries.append(idx)
            blocked_through = idx + h - 1

    events = full.loc[entries].copy()
    if events.empty:
        summary = pd.DataFrame([{
            "horizon_observations": h,
            "signal_threshold_abs_z": signal_threshold,
            "events": 0,
            "gross_hit_rate": np.nan,
            "avg_gross_pair_return_bp": np.nan,
            "avg_net_pair_return_bp": np.nan,
            "net_positive_rate": np.nan,
            "pair_transaction_cost_bp": pair_transaction_cost_bp,
        }])
        return events, summary

    events["trade_direction"] = np.where(events["hist_z"] > 0, "Long CITI / Short JPM", "Short CITI / Long JPM")
    events["exit_date"] = [full.loc[i + h, "date"] if i + h < len(full) else pd.NaT for i in entries]
    events["gross_pair_return_bp"] = events[ret]
    events["net_pair_return_bp"] = events["gross_pair_return_bp"] - float(pair_transaction_cost_bp)
    events["convergence_hit"] = events[conv] > 0
    events["net_positive"] = events["net_pair_return_bp"] > 0
    events["realized_convergence_ratio"] = events[ratio]

    keep = [
        "date", "exit_date", "hist_z", "pair_spread_bp", "hist_mean_bp",
        "deviation_from_mean_bp", "trade_direction", future, conv,
        "matched_duration", "realized_convergence_ratio", "gross_pair_return_bp",
        "net_pair_return_bp", "convergence_hit", "net_positive",
    ]
    events = events[keep].reset_index(drop=True)

    summary = pd.DataFrame([{
        "horizon_observations": h,
        "signal_threshold_abs_z": signal_threshold,
        "events": int(len(events)),
        "avg_signed_convergence_bp": events[conv].mean(),
        "median_signed_convergence_bp": events[conv].median(),
        "gross_hit_rate": events["convergence_hit"].mean(),
        "avg_gross_pair_return_bp": events["gross_pair_return_bp"].mean(),
        "median_gross_pair_return_bp": events["gross_pair_return_bp"].median(),
        "avg_net_pair_return_bp": events["net_pair_return_bp"].mean(),
        "median_net_pair_return_bp": events["net_pair_return_bp"].median(),
        "net_positive_rate": events["net_positive"].mean(),
        "avg_realized_convergence_ratio": events["realized_convergence_ratio"].mean(),
        "avg_clipped_convergence_ratio": events["realized_convergence_ratio"].clip(0.0, 1.0).mean(),
        "pair_transaction_cost_bp": float(pair_transaction_cost_bp),
    }])
    return events, summary


def assess_validation(
    signal_summary: pd.DataFrame,
    event_summary: pd.DataFrame,
    *,
    primary_horizon: int = 20,
    min_independent_events: int = 5,
) -> tuple[str, str, str]:
    """Gate a raw RV signal with historical validation.

    Returns (validation_status, pm_decision, reason). The rule is deliberately
    conservative: negative average signal-day performance is a failure, while a
    small number of independent events is treated as insufficient evidence.
    """
    s = signal_summary.loc[signal_summary["horizon_observations"] == int(primary_horizon)]
    e = event_summary.loc[event_summary["horizon_observations"] == int(primary_horizon)]
    if s.empty or e.empty:
        return "Insufficient evidence", "No trade", "Primary-horizon validation output is unavailable."

    sr = s.iloc[0]
    er = e.iloc[0]
    n_signal = int(sr.get("observations", 0))
    n_events = int(er.get("events", 0))
    avg_gross = float(sr.get("avg_gross_pair_return_bp", np.nan))
    hit = float(sr.get("convergence_hit_rate", np.nan))
    avg_net = float(er.get("avg_net_pair_return_bp", np.nan))
    net_pos = float(er.get("net_positive_rate", np.nan))

    if np.isfinite(avg_gross) and avg_gross <= 0:
        reason = (
            f"{primary_horizon}-observation signal-day average gross return is {avg_gross:.2f} bp "
            f"with a {hit:.1%} convergence hit rate; mean reversion is not supported."
        )
        return "Not supported", "No trade", reason

    if n_events < int(min_independent_events):
        reason = (
            f"Only {n_events} independent {primary_horizon}-observation event(s) are available "
            f"(minimum {min_independent_events}); evidence is too sparse for a portfolio trade."
        )
        return "Insufficient evidence", "No trade", reason

    if np.isfinite(avg_net) and np.isfinite(net_pos) and avg_net > 0 and net_pos > 0.5 and hit > 0.5:
        reason = (
            f"{primary_horizon}-observation validation is positive across signal-day and independent-event tests."
        )
        return "Supported", "Candidate trade", reason

    reason = (
        f"{primary_horizon}-observation validation does not clear the profitability/consistency gate "
        f"after transaction costs."
    )
    return "Not supported", "No trade", reason
