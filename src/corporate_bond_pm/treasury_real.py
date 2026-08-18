from __future__ import annotations

from datetime import date
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

TREASURY_XML = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
    "?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
)

TENOR_TAGS = {
    "BC_1MONTH": 1 / 12, "BC_1_5MONTH": 1.5 / 12, "BC_2MONTH": 2 / 12,
    "BC_3MONTH": 3 / 12, "BC_4MONTH": 4 / 12, "BC_6MONTH": 6 / 12,
    "BC_1YEAR": 1.0, "BC_2YEAR": 2.0, "BC_3YEAR": 3.0, "BC_5YEAR": 5.0,
    "BC_7YEAR": 7.0, "BC_10YEAR": 10.0, "BC_20YEAR": 20.0, "BC_30YEAR": 30.0,
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_treasury_yield_curve_xml(raw: bytes | str) -> pd.DataFrame:
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    root = ET.fromstring(raw)
    rows: list[dict] = []
    for elem in root.iter():
        if _local(elem.tag) != "properties":
            continue
        values = {_local(ch.tag): ch.text for ch in list(elem)}
        if "NEW_DATE" not in values:
            continue
        row = {"date": pd.to_datetime(values["NEW_DATE"]).normalize()}
        for tag, yrs in TENOR_TAGS.items():
            val = values.get(tag)
            if val not in (None, ""):
                row[yrs] = float(val)
        rows.append(row)
    if not rows:
        raise ValueError("No Treasury yield-curve rows found in XML response")
    return pd.DataFrame(rows).drop_duplicates("date").sort_values("date").reset_index(drop=True)


def fetch_treasury_yield_curve_year(year: int) -> pd.DataFrame:
    req = Request(TREASURY_XML.format(year=int(year)), headers={"User-Agent": "corporate-bond-portfolio-research/1.0"})
    with urlopen(req, timeout=30) as response:
        return parse_treasury_yield_curve_xml(response.read())


def fetch_treasury_yield_curve_range(start: date | str, end: date | str) -> pd.DataFrame:
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    frames = [fetch_treasury_yield_curve_year(y) for y in range(start_ts.year, end_ts.year + 1)]
    out = pd.concat(frames, ignore_index=True).drop_duplicates("date").sort_values("date")
    return out.loc[out["date"].between(start_ts, end_ts)].reset_index(drop=True)


def interpolate_curve_row(row: pd.Series, target_years: float) -> float:
    pts = [(float(c), float(row[c])) for c in row.index if isinstance(c, (int, float)) and pd.notna(row[c])]
    pts.sort()
    if len(pts) < 2:
        raise ValueError("At least two Treasury tenors are needed for interpolation")
    xs = np.array([p[0] for p in pts])
    ys = np.array([p[1] for p in pts])
    target = float(target_years)
    if target <= xs[0]: return float(ys[0])
    if target >= xs[-1]: return float(ys[-1])
    return float(np.interp(target, xs, ys))


def attach_treasury_proxy(daily: pd.DataFrame, treasury: pd.DataFrame, *, call_date: date | str, tolerance_days: int = 4) -> pd.DataFrame:
    x = daily.sort_values("date").copy()
    t = treasury.sort_values("date").copy()
    merged = pd.merge_asof(x, t, on="date", direction="backward", tolerance=pd.Timedelta(days=tolerance_days))
    call_ts = pd.Timestamp(call_date).normalize()
    merged["years_to_call"] = (call_ts - merged["date"]).dt.days / 365.25
    merged["treasury_yield_pct"] = merged.apply(
        lambda r: interpolate_curve_row(r, r["years_to_call"]) if r["years_to_call"] > 0 else np.nan,
        axis=1,
    )
    return merged
