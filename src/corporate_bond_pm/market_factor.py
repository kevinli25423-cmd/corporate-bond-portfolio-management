from __future__ import annotations

from io import BytesIO
from urllib.request import Request, urlopen

import pandas as pd

FRED_IG_OAS_SERIES = "BAMLC0A0CM"
FRED_IG_OAS_URL = (
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + FRED_IG_OAS_SERIES
)


def fetch_fred_ig_oas(start, end) -> pd.DataFrame:
    """Fetch ICE BofA US Corporate Index OAS from FRED (percent, daily)."""
    req = Request(
        FRED_IG_OAS_URL,
        headers={"User-Agent": "corporate-bond-portfolio-research/1.0"},
    )
    with urlopen(req, timeout=30) as response:
        raw = response.read()
    df = pd.read_csv(BytesIO(raw))
    date_col = df.columns[0]
    value_col = FRED_IG_OAS_SERIES
    if value_col not in df.columns:
        raise ValueError(f"FRED response did not contain {value_col}")
    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], errors="coerce").dt.normalize(),
        "ig_oas_pct": pd.to_numeric(df[value_col], errors="coerce"),
    }).dropna()
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    return (
        out.loc[out["date"].between(start_ts - pd.Timedelta(days=7), end_ts)]
        .drop_duplicates("date")
        .sort_values("date")
        .reset_index(drop=True)
    )


def attach_ig_systematic_factor(
    panel: pd.DataFrame,
    factor: pd.DataFrame,
    *,
    tolerance_days: int = 4,
) -> pd.DataFrame:
    """
    Attach the broad IG OAS level and change to the bond panel.

    The change is measured between the factor observations aligned to consecutive
    bond-panel dates, so it is in the same observation cadence as the pair.
    """
    x = panel.sort_values("date").copy()
    f = factor.sort_values("date").copy()
    merged = pd.merge_asof(
        x,
        f,
        on="date",
        direction="backward",
        tolerance=pd.Timedelta(days=tolerance_days),
    )
    merged["systematic_credit_factor_change_bp"] = merged["ig_oas_pct"].diff() * 100.0
    return merged
