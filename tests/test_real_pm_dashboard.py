import numpy as np
import pandas as pd

from corporate_bond_pm.real_risk_decomposition import (
    add_factor_decomposition,
    build_cob_risk_snapshot,
    build_pair_risk_summary,
    build_stress_table,
)


def make_panel(n=150):
    dates = pd.date_range("2025-01-02", periods=n, freq="B")
    t = np.arange(n, dtype=float)

    common = 0.10 * np.sin(t / 9.0)
    citi_spread = 60.0 + np.cumsum(common + 0.03 * np.sin(t / 5.0))
    jpm_spread = 55.0 + np.cumsum(common - 0.02 * np.sin(t / 6.0))
    citi_tsy = 4.0 + 0.001 * np.sin(t / 11.0)
    jpm_tsy = 4.1 + 0.001 * np.cos(t / 13.0)

    return pd.DataFrame({
        "date": dates,
        "CITI_representative_price": 98.0 - 0.01*t,
        "JPM_representative_price": 94.0 - 0.008*t,
        "CITI_displayed_volume": 1_000_000 + 100_000*(1 + np.sin(t/7.0)),
        "JPM_displayed_volume": 1_200_000 + 120_000*(1 + np.cos(t/8.0)),
        "CITI_ytc_pct": citi_tsy + citi_spread/100.0,
        "JPM_ytc_pct": jpm_tsy + jpm_spread/100.0,
        "CITI_duration_to_call": np.full(n, 2.4),
        "JPM_duration_to_call": np.full(n, 2.9),
        "CITI_treasury_yield_pct": citi_tsy,
        "JPM_treasury_yield_pct": jpm_tsy,
        "CITI_treasury_spread_bp": citi_spread,
        "JPM_treasury_spread_bp": jpm_spread,
        "pair_spread_bp": citi_spread - jpm_spread,
        "hist_z": np.linspace(-1.5, -1.0, n),
    })


def test_factor_identity_reconciles():
    x = add_factor_decomposition(
        make_panel(), regression_window=80, min_regression_observations=40
    )
    r = x.iloc[-1]
    for issuer in ("CITI", "JPM"):
        rhs = (
            r[f"{issuer}_d_treasury_bp"]
            + r[f"{issuer}_systematic_credit_bp"]
            + r[f"{issuer}_liquidity_contribution_bp"]
            + r[f"{issuer}_idiosyncratic_credit_bp"]
        )
        assert abs(r[f"{issuer}_d_ytc_bp"] - rhs) < 1e-8


def test_risk_snapshot_has_dv01_and_cs01():
    x = add_factor_decomposition(
        make_panel(), regression_window=80, min_regression_observations=40
    )
    risk = build_cob_risk_snapshot(x)
    assert set(risk["issuer"]) == {"CITI", "JPM"}
    assert (risk["dv01_usd_per_bp"] > 0).all()
    assert (risk["cs01_usd_per_bp"] > 0).all()


def test_reference_pair_is_dv01_neutral():
    x = add_factor_decomposition(
        make_panel(), regression_window=80, min_regression_observations=40
    )
    risk = build_cob_risk_snapshot(x)
    pair = build_pair_risk_summary(x, risk).iloc[0]
    assert abs(pair["net_dv01_usd_per_bp"]) < 1e-8


def test_stress_table_returns_all_scenarios():
    x = add_factor_decomposition(
        make_panel(), regression_window=80, min_regression_observations=40
    )
    risk = build_cob_risk_snapshot(x)
    pair = build_pair_risk_summary(x, risk)
    scenarios = {
        "Rates": {"rates_bp": 50},
        "Credit": {"common_credit_bp": 25},
        "Idio": {"citi_idio_bp": 20},
    }
    stress = build_stress_table(pair, risk, scenarios)
    assert list(stress["scenario"]) == ["Rates", "Credit", "Idio"]
    assert stress["pair_pnl_usd"].notna().all()
