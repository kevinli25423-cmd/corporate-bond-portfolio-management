from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import pandas as pd


@dataclass
class ProjectData:
    security_master: pd.DataFrame
    market_daily: pd.DataFrame
    cds_daily: pd.DataFrame
    fundamentals: pd.DataFrame
    liquidity_daily: pd.DataFrame
    holdings: pd.DataFrame
    config: dict


def load_project_data(root: str | Path) -> ProjectData:
    root = Path(root)
    demo = root / "data" / "demo"
    with open(root / "config" / "project_config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    return ProjectData(
        security_master=pd.read_csv(demo / "security_master.csv", parse_dates=["maturity", "issue_date"]),
        market_daily=pd.read_csv(demo / "market_daily.csv", parse_dates=["date"]),
        cds_daily=pd.read_csv(demo / "cds_daily.csv", parse_dates=["date"]),
        fundamentals=pd.read_csv(demo / "fundamentals.csv", parse_dates=["effective_date"]),
        liquidity_daily=pd.read_csv(demo / "liquidity_daily.csv", parse_dates=["date"]),
        holdings=pd.read_csv(demo / "holdings.csv"),
        config=config,
    )


def latest_snapshot(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    latest = df[date_col].max()
    return df.loc[df[date_col].eq(latest)].copy()


def point_in_time_fundamentals(fundamentals: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Use only fundamental observations that were available by the analysis date."""
    f = fundamentals.loc[fundamentals["effective_date"] <= as_of].copy()
    f = f.sort_values(["issuer", "effective_date"])
    return f.groupby("issuer", as_index=False).tail(1)
