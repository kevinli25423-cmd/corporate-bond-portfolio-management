from __future__ import annotations

import numpy as np
import pandas as pd

from .risk import bond_cs01, bond_dv01, krd_weights


def _ols_beta(y: np.ndarray, common: np.ndarray, liquidity: np.ndarray) -> tuple[float, float]:
    X = np.column_stack([np.ones(len(y)), common, liquidity])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return float(beta[1]), float(beta[2])


def add_factor_decomposition(
    pair: pd.DataFrame,
    *,
    regression_window: int = 120,
    min_regression_observations: int = 60,
    liquidity_shock_clip: float = 3.0,
) -> pd.DataFrame:
    """
    Add a lagged close-of-business factor decomposition.

    Accounting identity:
        dYTC = dTreasury + dSpread

    Spread decomposition:
        dSpread = systematic credit proxy + liquidity contribution + idiosyncratic residual

    In production, ``systematic_credit_factor_change_bp`` is attached from the
    ICE BofA US Corporate Index OAS series obtained through FRED. If that column
    is absent (for unit tests only), a pair-common fallback is used. The liquidity
    contribution is estimated with a trailing regression on the available reported-
    volume shock. Coefficients at date t use observations strictly before t.
    """
    x = pair.sort_values("date").reset_index(drop=True).copy()

    for issuer in ("CITI", "JPM"):
        x[f"{issuer}_d_price"] = x[f"{issuer}_representative_price"].diff()
        x[f"{issuer}_d_ytc_bp"] = x[f"{issuer}_ytc_pct"].diff() * 100.0
        x[f"{issuer}_d_treasury_bp"] = x[f"{issuer}_treasury_yield_pct"].diff() * 100.0
        x[f"{issuer}_d_spread_bp"] = x[f"{issuer}_treasury_spread_bp"].diff()

        vol = pd.to_numeric(x[f"{issuer}_displayed_volume"], errors="coerce")
        vol = vol.where(vol > 0)
        x[f"{issuer}_log_volume"] = np.log(vol)
        # Positive shock = lower displayed volume than the prior observation.
        x[f"{issuer}_liquidity_shock"] = (
            -x[f"{issuer}_log_volume"].diff()
        ).clip(-float(liquidity_shock_clip), float(liquidity_shock_clip))

    if "systematic_credit_factor_change_bp" not in x.columns:
        x["systematic_credit_factor_change_bp"] = 0.5 * (
            x["CITI_d_spread_bp"] + x["JPM_d_spread_bp"]
        )
        x["systematic_factor_source"] = "pair-common fallback"
    else:
        x["systematic_factor_source"] = "ICE BofA US Corporate Index OAS via FRED"

    x["pair_spread_change_bp"] = x["CITI_d_spread_bp"] - x["JPM_d_spread_bp"]

    for issuer in ("CITI", "JPM"):
        beta_sys = np.full(len(x), np.nan)
        beta_liq = np.full(len(x), np.nan)

        for i in range(len(x)):
            lo = max(1, i - int(regression_window))
            hist = x.iloc[lo:i][[
                f"{issuer}_d_spread_bp",
                "systematic_credit_factor_change_bp",
                f"{issuer}_liquidity_shock",
            ]].dropna()

            if len(hist) < int(min_regression_observations):
                continue

            b_sys, b_liq = _ols_beta(
                hist[f"{issuer}_d_spread_bp"].to_numpy(float),
                hist["systematic_credit_factor_change_bp"].to_numpy(float),
                hist[f"{issuer}_liquidity_shock"].to_numpy(float),
            )
            beta_sys[i] = b_sys
            beta_liq[i] = b_liq

        x[f"{issuer}_beta_systematic"] = beta_sys
        x[f"{issuer}_beta_liquidity"] = beta_liq
        x[f"{issuer}_systematic_credit_bp"] = (
            x[f"{issuer}_beta_systematic"] * x["systematic_credit_factor_change_bp"]
        )
        x[f"{issuer}_liquidity_contribution_bp"] = (
            x[f"{issuer}_beta_liquidity"] * x[f"{issuer}_liquidity_shock"]
        )

        fallback = x[f"{issuer}_systematic_credit_bp"].isna()
        x.loc[fallback, f"{issuer}_systematic_credit_bp"] = x.loc[
            fallback, "systematic_credit_factor_change_bp"
        ]
        x.loc[fallback, f"{issuer}_liquidity_contribution_bp"] = 0.0

        x[f"{issuer}_idiosyncratic_credit_bp"] = (
            x[f"{issuer}_d_spread_bp"]
            - x[f"{issuer}_systematic_credit_bp"]
            - x[f"{issuer}_liquidity_contribution_bp"]
        )

        x[f"{issuer}_factor_reconciliation_bp"] = (
            x[f"{issuer}_d_ytc_bp"]
            - x[f"{issuer}_d_treasury_bp"]
            - x[f"{issuer}_systematic_credit_bp"]
            - x[f"{issuer}_liquidity_contribution_bp"]
            - x[f"{issuer}_idiosyncratic_credit_bp"]
        )

    return x


def _risk_for_face(price: float, duration: float, face: float) -> tuple[float, float, float]:
    market_value = float(face) * float(price) / 100.0
    dv01 = bond_dv01(market_value, float(duration))
    # Transparent approximation within this public-data implementation.
    cs01 = bond_cs01(market_value, float(duration))
    return market_value, dv01, cs01


def build_cob_risk_snapshot(
    panel: pd.DataFrame,
    *,
    base_face_notional_usd: float = 10_000_000.0,
) -> pd.DataFrame:
    complete = panel.dropna(subset=["CITI_d_ytc_bp", "JPM_d_ytc_bp"])
    if complete.empty:
        raise ValueError("No complete close-of-business changes are available.")

    cur_idx = int(complete.index[-1])
    cur = panel.loc[cur_idx]
    prev = panel.loc[cur_idx - 1]
    rows = []

    for issuer in ("CITI", "JPM"):
        mv, dv01, cs01 = _risk_for_face(
            cur[f"{issuer}_representative_price"],
            cur[f"{issuer}_duration_to_call"],
            base_face_notional_usd,
        )
        _, prev_dv01, prev_cs01 = _risk_for_face(
            prev[f"{issuer}_representative_price"],
            prev[f"{issuer}_duration_to_call"],
            base_face_notional_usd,
        )

        rates_bp = float(cur[f"{issuer}_d_treasury_bp"])
        systematic_bp = float(cur[f"{issuer}_systematic_credit_bp"])
        liquidity_bp = float(cur[f"{issuer}_liquidity_contribution_bp"])
        idio_bp = float(cur[f"{issuer}_idiosyncratic_credit_bp"])

        rate_pnl = -prev_dv01 * rates_bp
        systematic_pnl = -prev_cs01 * systematic_bp
        liquidity_pnl = -prev_cs01 * liquidity_bp
        idio_pnl = -prev_cs01 * idio_bp
        factor_pnl = rate_pnl + systematic_pnl + liquidity_pnl + idio_pnl
        clean_price_pnl = base_face_notional_usd * float(cur[f"{issuer}_d_price"]) / 100.0

        vh = pd.to_numeric(
            panel.loc[:cur_idx, f"{issuer}_displayed_volume"], errors="coerce"
        ).dropna()
        current_volume = pd.to_numeric(
            pd.Series([cur[f"{issuer}_displayed_volume"]]), errors="coerce"
        ).iloc[0]
        median20 = float(vh.tail(20).median()) if len(vh) else np.nan
        volume_ratio = (
            float(current_volume / median20)
            if np.isfinite(current_volume) and np.isfinite(median20) and median20 > 0
            else np.nan
        )
        spread_vol20 = float(
            pd.to_numeric(
                panel.loc[:cur_idx, f"{issuer}_treasury_spread_bp"], errors="coerce"
            ).tail(20).diff().std(ddof=1)
        )

        rows.append({
            "as_of": pd.Timestamp(cur["date"]).date().isoformat(),
            "prior_date": pd.Timestamp(prev["date"]).date().isoformat(),
            "issuer": issuer,
            "face_notional_usd": float(base_face_notional_usd),
            "market_value_usd": mv,
            "price": float(cur[f"{issuer}_representative_price"]),
            "price_change": float(cur[f"{issuer}_d_price"]),
            "ytc_pct": float(cur[f"{issuer}_ytc_pct"]),
            "ytc_change_bp": float(cur[f"{issuer}_d_ytc_bp"]),
            "treasury_yield_pct": float(cur[f"{issuer}_treasury_yield_pct"]),
            "treasury_change_bp": rates_bp,
            "treasury_spread_bp": float(cur[f"{issuer}_treasury_spread_bp"]),
            "spread_change_bp": float(cur[f"{issuer}_d_spread_bp"]),
            "duration_to_call": float(cur[f"{issuer}_duration_to_call"]),
            "spread_duration_proxy": float(cur[f"{issuer}_duration_to_call"]),
            "dv01_usd_per_bp": dv01,
            "cs01_usd_per_bp": cs01,
            "systematic_credit_bp": systematic_bp,
            "liquidity_contribution_bp": liquidity_bp,
            "idiosyncratic_credit_bp": idio_bp,
            "displayed_volume": float(current_volume) if np.isfinite(current_volume) else np.nan,
            "median_displayed_volume_20obs": median20,
            "volume_vs_20obs_median": volume_ratio,
            "spread_change_volatility_20obs_bp": spread_vol20,
            "liquidity_shock": (
                float(cur[f"{issuer}_liquidity_shock"])
                if pd.notna(cur[f"{issuer}_liquidity_shock"]) else np.nan
            ),
            "rate_pnl_usd_long": rate_pnl,
            "systematic_credit_pnl_usd_long": systematic_pnl,
            "liquidity_pnl_usd_long": liquidity_pnl,
            "idiosyncratic_credit_pnl_usd_long": idio_pnl,
            "factor_pnl_usd_long": factor_pnl,
            "clean_price_pnl_usd_long": clean_price_pnl,
            "pricing_residual_pnl_usd_long": clean_price_pnl - factor_pnl,
        })

    return pd.DataFrame(rows)


def build_krd_snapshot(risk_snapshot: pd.DataFrame) -> pd.DataFrame:
    as_of = pd.Timestamp(risk_snapshot["as_of"].iloc[0])
    call_dates = {
        "CITI": pd.Timestamp("2029-03-20"),
        "JPM": pd.Timestamp("2029-10-15"),
    }

    rows = []
    for r in risk_snapshot.itertuples():
        years = max((call_dates[r.issuer] - as_of).days / 365.25, 1.0 / 365.25)
        row = {
            "as_of": r.as_of,
            "issuer": r.issuer,
            "years_to_first_par_call": years,
            "dv01_usd_per_bp": r.dv01_usd_per_bp,
        }
        for node, weight in krd_weights(years).items():
            row[node] = r.dv01_usd_per_bp * weight
        rows.append(row)

    return pd.DataFrame(rows)


def build_pair_risk_summary(
    panel: pd.DataFrame,
    risk_snapshot: pd.DataFrame,
    *,
    base_citi_face_usd: float = 10_000_000.0,
) -> pd.DataFrame:
    rs = risk_snapshot.set_index("issuer")
    citi = rs.loc["CITI"]
    jpm = rs.loc["JPM"]

    citi_face = float(base_citi_face_usd)
    jpm_face = citi_face * float(citi.dv01_usd_per_bp) / float(jpm.dv01_usd_per_bp)
    citi_scale = citi_face / float(citi.face_notional_usd)
    jpm_scale = jpm_face / float(jpm.face_notional_usd)

    latest = panel.dropna(subset=["hist_z"]).iloc[-1]
    if float(latest["hist_z"]) >= 0:
        citi_sign, jpm_sign = 1.0, -1.0
        direction = "Long CITI / Short JPM"
    else:
        citi_sign, jpm_sign = -1.0, 1.0
        direction = "Short CITI / Long JPM"

    citi_dv01 = citi_scale * float(citi.dv01_usd_per_bp)
    jpm_dv01 = jpm_scale * float(jpm.dv01_usd_per_bp)
    citi_cs01 = citi_scale * float(citi.cs01_usd_per_bp)
    jpm_cs01 = jpm_scale * float(jpm.cs01_usd_per_bp)

    def factor_pair(col: str) -> float:
        return (
            citi_sign * citi_scale * float(citi[col])
            + jpm_sign * jpm_scale * float(jpm[col])
        )

    return pd.DataFrame([{
        "as_of": pd.Timestamp(latest["date"]).date().isoformat(),
        "direction": direction,
        "citi_face_usd": citi_face,
        "jpm_face_usd_dv01_hedged": jpm_face,
        "jpm_per_citi_face_ratio": jpm_face / citi_face,
        "citi_position_market_value_usd": citi_sign * citi_scale * float(citi.market_value_usd),
        "jpm_position_market_value_usd": jpm_sign * jpm_scale * float(jpm.market_value_usd),
        "gross_market_value_usd": (
            abs(citi_scale * float(citi.market_value_usd))
            + abs(jpm_scale * float(jpm.market_value_usd))
        ),
        "net_market_value_usd": (
            citi_sign * citi_scale * float(citi.market_value_usd)
            + jpm_sign * jpm_scale * float(jpm.market_value_usd)
        ),
        "citi_position_dv01_usd_per_bp": citi_sign * citi_dv01,
        "jpm_position_dv01_usd_per_bp": jpm_sign * jpm_dv01,
        "net_dv01_usd_per_bp": citi_sign * citi_dv01 + jpm_sign * jpm_dv01,
        "gross_dv01_usd_per_bp": abs(citi_dv01) + abs(jpm_dv01),
        "citi_position_cs01_usd_per_bp": citi_sign * citi_cs01,
        "jpm_position_cs01_usd_per_bp": jpm_sign * jpm_cs01,
        "net_cs01_usd_per_bp": citi_sign * citi_cs01 + jpm_sign * jpm_cs01,
        "gross_cs01_usd_per_bp": abs(citi_cs01) + abs(jpm_cs01),
        "pair_spread_change_bp": float(latest["pair_spread_change_bp"]),
        "rate_pnl_usd": factor_pair("rate_pnl_usd_long"),
        "systematic_credit_pnl_usd": factor_pair("systematic_credit_pnl_usd_long"),
        "liquidity_pnl_usd": factor_pair("liquidity_pnl_usd_long"),
        "idiosyncratic_credit_pnl_usd": factor_pair("idiosyncratic_credit_pnl_usd_long"),
        "factor_pnl_usd": factor_pair("factor_pnl_usd_long"),
        "clean_price_pnl_usd": factor_pair("clean_price_pnl_usd_long"),
        "pricing_residual_pnl_usd": factor_pair("pricing_residual_pnl_usd_long"),
    }])


def build_stress_table(
    pair_risk: pd.DataFrame,
    risk_snapshot: pd.DataFrame,
    scenarios: dict,
) -> pd.DataFrame:
    pr = pair_risk.iloc[0]
    rs = risk_snapshot.set_index("issuer")

    citi_face_scale = abs(float(pr.citi_face_usd)) / float(rs.loc["CITI", "face_notional_usd"])
    jpm_face_scale = abs(float(pr.jpm_face_usd_dv01_hedged)) / float(rs.loc["JPM", "face_notional_usd"])

    citi_sign = 1.0 if float(pr.citi_position_dv01_usd_per_bp) > 0 else -1.0
    jpm_sign = 1.0 if float(pr.jpm_position_dv01_usd_per_bp) > 0 else -1.0

    citi_dv01 = citi_face_scale * float(rs.loc["CITI", "dv01_usd_per_bp"])
    jpm_dv01 = jpm_face_scale * float(rs.loc["JPM", "dv01_usd_per_bp"])
    citi_cs01 = citi_face_scale * float(rs.loc["CITI", "cs01_usd_per_bp"])
    jpm_cs01 = jpm_face_scale * float(rs.loc["JPM", "cs01_usd_per_bp"])

    rows = []
    for name, shock in scenarios.items():
        rates = float(shock.get("rates_bp", 0.0))
        common = float(shock.get("common_credit_bp", 0.0))
        citi_idio = float(shock.get("citi_idio_bp", 0.0))
        jpm_idio = float(shock.get("jpm_idio_bp", 0.0))
        common_liquidity = float(shock.get("liquidity_bp", 0.0))
        citi_liquidity = float(shock.get("citi_liquidity_bp", common_liquidity))
        jpm_liquidity = float(shock.get("jpm_liquidity_bp", common_liquidity))

        citi_pnl = (
            -citi_sign * citi_dv01 * rates
            -citi_sign * citi_cs01 * (common + citi_idio + citi_liquidity)
        )
        jpm_pnl = (
            -jpm_sign * jpm_dv01 * rates
            -jpm_sign * jpm_cs01 * (common + jpm_idio + jpm_liquidity)
        )

        rows.append({
            "scenario": name,
            "rates_bp": rates,
            "common_credit_bp": common,
            "citi_idio_bp": citi_idio,
            "jpm_idio_bp": jpm_idio,
            "citi_liquidity_bp": citi_liquidity,
            "jpm_liquidity_bp": jpm_liquidity,
            "citi_pnl_usd": citi_pnl,
            "jpm_pnl_usd": jpm_pnl,
            "pair_pnl_usd": citi_pnl + jpm_pnl,
        })

    return pd.DataFrame(rows)
