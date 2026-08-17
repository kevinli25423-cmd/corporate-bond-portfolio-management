from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from .relative_value import historical_pair_signal


@dataclass(frozen=True)
class PairBacktestConfig:
    window: int = 252
    min_history: int = 60
    signal_threshold: float = 1.0
    horizons: tuple[int, ...] = (5, 20, 60)
    event_horizon: int = 20
    pair_transaction_cost_bp: float = 8.0


def build_pair_validation_panel(
    market_daily: pd.DataFrame,
    sec_a: str,
    sec_b: str,
    *,
    window: int = 252,
    min_history: int = 60,
    horizons: Iterable[int] = (5, 20, 60),
) -> pd.DataFrame:
    """Create a chronological pair-RV validation panel without look-ahead in the signal.

    The historical mean/std are lagged inside ``historical_pair_signal``. Future
    outcomes are appended only for evaluation after the signal has been formed.

    Positive ``hist_z`` means A is wide versus B. The signed convergence measure
    is positive when the pair subsequently moves in the direction implied by the
    signal, regardless of which side was initially cheap.
    """
    panel = historical_pair_signal(
        market_daily,
        sec_a,
        sec_b,
        window=window,
        min_history=min_history,
    )

    risk = market_daily.loc[
        market_daily["security_id"].isin([sec_a, sec_b]),
        ["date", "security_id", "spread_duration"],
    ].pivot(index="date", columns="security_id", values="spread_duration")
    risk["matched_spread_duration"] = risk[[sec_a, sec_b]].mean(axis=1)
    panel = panel.merge(
        risk[["matched_spread_duration"]].reset_index(),
        on="date",
        how="left",
    )

    panel["deviation_from_mean_bp"] = panel["pair_spread_bp"] - panel["hist_mean_bp"]
    panel["signal_direction"] = np.sign(panel["hist_z"])

    for horizon in horizons:
        future_change = panel["pair_spread_bp"].shift(-horizon) - panel["pair_spread_bp"]
        signed_convergence = -panel["signal_direction"] * future_change
        panel[f"future_pair_change_{horizon}d_bp"] = future_change
        panel[f"signed_convergence_{horizon}d_bp"] = signed_convergence
        panel[f"gross_pair_return_{horizon}d_bp"] = (
            panel["matched_spread_duration"] * signed_convergence
        )
        denom = panel["deviation_from_mean_bp"].abs().replace(0.0, np.nan)
        panel[f"realized_convergence_ratio_{horizon}d"] = signed_convergence / denom

    return panel


def summarize_signal_days(
    panel: pd.DataFrame,
    *,
    signal_threshold: float = 1.0,
    horizons: Iterable[int] = (5, 20, 60),
) -> pd.DataFrame:
    """Summarize all daily observations where |z| exceeds the signal threshold.

    These are validation observations rather than independent trades; consecutive
    signal days can overlap. Independent non-overlapping events are handled by
    ``independent_event_backtest``.
    """
    rows: list[dict] = []
    for horizon in horizons:
        conv_col = f"signed_convergence_{horizon}d_bp"
        ret_col = f"gross_pair_return_{horizon}d_bp"
        q_col = f"realized_convergence_ratio_{horizon}d"
        x = panel.loc[panel["hist_z"].abs() >= signal_threshold].dropna(
            subset=[conv_col, ret_col]
        )
        corr = np.nan
        if len(x) > 1 and x["hist_z"].abs().std(ddof=1) > 0 and x[conv_col].std(ddof=1) > 0:
            corr = x["hist_z"].abs().corr(x[conv_col])
        rows.append({
            "horizon_days": horizon,
            "signal_threshold_abs_z": signal_threshold,
            "observations": len(x),
            "avg_signed_convergence_bp": x[conv_col].mean(),
            "median_signed_convergence_bp": x[conv_col].median(),
            "convergence_hit_rate": (x[conv_col] > 0).mean(),
            "avg_gross_pair_return_bp": x[ret_col].mean(),
            "median_gross_pair_return_bp": x[ret_col].median(),
            "abs_z_vs_convergence_corr": corr,
            "avg_realized_convergence_ratio": x[q_col].mean(),
            "avg_clipped_convergence_ratio": x[q_col].clip(0.0, 1.0).mean(),
        })
    return pd.DataFrame(rows)


def independent_event_backtest(
    panel: pd.DataFrame,
    *,
    signal_threshold: float = 1.0,
    horizon_days: int = 20,
    pair_transaction_cost_bp: float = 8.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Backtest non-overlapping threshold-crossing events.

    An event starts when |z| crosses the threshold from below. A new event is not
    allowed until the prior holding horizon has elapsed. This avoids treating
    every consecutive signal day as an independent trade.

    ``pair_transaction_cost_bp`` is a transparent all-in implementation-cost
    assumption for the two-leg pair. It is subtracted once from gross pair return.
    """
    conv_col = f"signed_convergence_{horizon_days}d_bp"
    ret_col = f"gross_pair_return_{horizon_days}d_bp"
    future_col = f"future_pair_change_{horizon_days}d_bp"
    required = ["hist_z", conv_col, ret_col, future_col]
    x = panel.dropna(subset=required).reset_index(drop=True).copy()

    entries: list[int] = []
    blocked_through = -1
    for i, row in x.iterrows():
        if i <= blocked_through:
            continue
        prev_abs = abs(float(x.loc[i - 1, "hist_z"])) if i > 0 else 0.0
        if abs(float(row["hist_z"])) >= signal_threshold and prev_abs < signal_threshold:
            entries.append(i)
            blocked_through = i + horizon_days - 1

    events = x.loc[entries].copy()
    if events.empty:
        summary = pd.DataFrame([{
            "horizon_days": horizon_days,
            "signal_threshold_abs_z": signal_threshold,
            "events": 0,
            "avg_signed_convergence_bp": np.nan,
            "gross_hit_rate": np.nan,
            "avg_gross_pair_return_bp": np.nan,
            "avg_net_pair_return_bp": np.nan,
            "net_positive_rate": np.nan,
            "pair_transaction_cost_bp": pair_transaction_cost_bp,
        }])
        return events, summary

    events["trade_direction"] = np.where(
        events["hist_z"] > 0,
        "Long A / Short B",
        "Short A / Long B",
    )
    events["exit_date"] = events["date"].shift(-horizon_days)
    # The shift above is not valid after filtering to event rows; map exits from
    # the original panel by business-row position instead.
    date_lookup = panel.reset_index(drop=True)["date"]
    original_index = panel.reset_index().set_index("date")["index"]
    exit_dates = []
    for date in events["date"]:
        idx = int(original_index.loc[date])
        exit_idx = idx + horizon_days
        exit_dates.append(date_lookup.iloc[exit_idx] if exit_idx < len(date_lookup) else pd.NaT)
    events["exit_date"] = exit_dates

    events["gross_pair_return_bp"] = events[ret_col]
    events["net_pair_return_bp"] = events["gross_pair_return_bp"] - pair_transaction_cost_bp
    events["convergence_hit"] = events[conv_col] > 0
    events["net_positive"] = events["net_pair_return_bp"] > 0
    events["realized_convergence_ratio"] = events[
        f"realized_convergence_ratio_{horizon_days}d"
    ]

    keep = [
        "date",
        "exit_date",
        "hist_z",
        "pair_spread_bp",
        "hist_mean_bp",
        "deviation_from_mean_bp",
        "trade_direction",
        future_col,
        conv_col,
        "matched_spread_duration",
        "realized_convergence_ratio",
        "gross_pair_return_bp",
        "net_pair_return_bp",
        "convergence_hit",
        "net_positive",
    ]
    events = events[keep].reset_index(drop=True)

    summary = pd.DataFrame([{
        "horizon_days": horizon_days,
        "signal_threshold_abs_z": signal_threshold,
        "events": len(events),
        "avg_signed_convergence_bp": events[conv_col].mean(),
        "median_signed_convergence_bp": events[conv_col].median(),
        "gross_hit_rate": events["convergence_hit"].mean(),
        "avg_gross_pair_return_bp": events["gross_pair_return_bp"].mean(),
        "median_gross_pair_return_bp": events["gross_pair_return_bp"].median(),
        "avg_net_pair_return_bp": events["net_pair_return_bp"].mean(),
        "median_net_pair_return_bp": events["net_pair_return_bp"].median(),
        "net_positive_rate": events["net_positive"].mean(),
        "avg_realized_convergence_ratio": events["realized_convergence_ratio"].mean(),
        "avg_clipped_convergence_ratio": events["realized_convergence_ratio"].clip(0.0, 1.0).mean(),
        "pair_transaction_cost_bp": pair_transaction_cost_bp,
    }])
    return events, summary
