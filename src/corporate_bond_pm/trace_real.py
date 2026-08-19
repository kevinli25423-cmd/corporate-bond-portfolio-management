from __future__ import annotations

from pathlib import Path
import re

import numpy as np
import pandas as pd


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


DATE_CANDIDATES = {
    "tradedate", "executiondate", "date", "effectivedate",
    "transactiondate", "tradeexecutiondate"
}
PRICE_CANDIDATES = {
    "price", "tradeprice", "executionprice", "lastprice",
    "lastsaleprice", "reportedprice"
}
VOLUME_CANDIDATES = {
    "quantity", "tradequantity", "volume", "tradevolume",
    "reportedtradevolume", "parvalue", "principalamount", "size"
}


def _detect_column(columns, candidates: set[str]) -> str | None:
    normalized = {_norm(c): c for c in columns}
    for key in candidates:
        if key in normalized:
            return normalized[key]
    for n, original in normalized.items():
        if any(key in n for key in candidates):
            return original
    return None


def _parse_volume_with_cap(value) -> tuple[float, bool]:
    """Parse FINRA displayed/reported volume, preserving whether it is capped."""
    if pd.isna(value):
        return np.nan, False
    raw = str(value).strip().upper().replace(",", "").replace("$", "")
    capped = raw.endswith("+")
    s = raw[:-1] if capped else raw
    multiplier = 1.0
    if s.endswith("MM"):
        multiplier, s = 1_000_000.0, s[:-2]
    elif s.endswith("M"):
        multiplier, s = 1_000_000.0, s[:-1]
    elif s.endswith("K"):
        multiplier, s = 1_000.0, s[:-1]
    try:
        return float(s) * multiplier, capped
    except ValueError:
        m = re.search(r"[-+]?[0-9]*\.?[0-9]+", s)
        return (float(m.group()) * multiplier if m else np.nan), capped


def _parse_volume(value) -> float:
    """Backward-compatible numeric lower-bound parser."""
    return _parse_volume_with_cap(value)[0]


def load_finra_trade_export(
    path: str | Path,
    *,
    date_col: str | None = None,
    price_col: str | None = None,
    volume_col: str | None = None,
) -> pd.DataFrame:
    """
    Normalize a locally stored FINRA fixed-income CSV.

    The project's current local files come from FINRA Corporate & Agency Bond
    Trade Activity (end-of-day rows). If a displayed volume is capped (for
    example, ``5MM+``), ``displayed_volume`` stores the disclosed lower bound
    and ``volume_is_capped`` records that the exact size is unknown.
    """
    path = Path(path)
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError(f"No rows found in {path}")

    date_col = date_col or _detect_column(df.columns, DATE_CANDIDATES)
    price_col = price_col or _detect_column(df.columns, PRICE_CANDIDATES)
    volume_col = volume_col or _detect_column(df.columns, VOLUME_CANDIDATES)
    if date_col is None or price_col is None:
        raise ValueError(
            "Could not detect FINRA date/price columns. "
            f"Columns found: {list(df.columns)}. Pass --date-col/--price-col explicitly."
        )

    out = pd.DataFrame()
    out["date"] = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
    out["price"] = pd.to_numeric(
        df[price_col].astype(str).str.replace(r"[^0-9.\-]", "", regex=True),
        errors="coerce",
    )

    if volume_col is not None:
        parsed = df[volume_col].map(_parse_volume_with_cap)
        out["displayed_volume"] = parsed.map(lambda z: z[0])
        out["volume_is_capped"] = parsed.map(lambda z: z[1])
    else:
        out["displayed_volume"] = np.nan
        out["volume_is_capped"] = False

    out = out.dropna(subset=["date", "price"])
    out = out.loc[out["price"].between(20.0, 180.0)].copy()
    out["source_row"] = out.index
    return out.sort_values(["date", "source_row"]).reset_index(drop=True)


def daily_trade_summary(
    trades: pd.DataFrame,
    *,
    representative: str = "median",
) -> pd.DataFrame:
    """
    Create one row per date.

    ``last_sale`` is the semantically appropriate method for the project's
    FINRA Trade Activity end-of-day files. ``median`` and ``vwap`` remain
    available for genuine transaction-level inputs.
    """
    if representative not in {"median", "vwap", "last_sale"}:
        raise ValueError("representative must be 'median', 'vwap', or 'last_sale'")

    rows = []
    for d, g in trades.groupby("date"):
        g = g.sort_values("source_row") if "source_row" in g.columns else g
        valid_vol = g["displayed_volume"].notna() & g["displayed_volume"].gt(0)
        vwap = np.nan
        if valid_vol.any():
            vwap = float(
                np.average(
                    g.loc[valid_vol, "price"],
                    weights=g.loc[valid_vol, "displayed_volume"],
                )
            )
        med = float(g["price"].median())
        last_sale = float(g["price"].iloc[-1])

        if representative == "median":
            rep = med
        elif representative == "vwap":
            rep = last_sale if np.isnan(vwap) else vwap
        else:
            rep = last_sale

        rows.append({
            "date": d,
            "trade_count": len(g),
            # For capped rows this is a disclosed lower bound, not exact volume.
            "displayed_volume": g["displayed_volume"].sum(min_count=1),
            "volume_has_cap": bool(g.get("volume_is_capped", pd.Series(False, index=g.index)).any()),
            "median_price": med,
            "vwap_price": vwap,
            "last_sale_price": last_sale,
            "representative_price": rep,
            "price_min": float(g["price"].min()),
            "price_max": float(g["price"].max()),
        })

    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
