import numpy as np
import pandas as pd
from corporate_bond_pm.real_risk_decomposition import add_factor_decomposition, build_cob_risk_snapshot, build_pair_risk_summary

def make_test_panel(n=150):
    dates=pd.date_range("2025-01-02",periods=n,freq="B"); t=np.arange(n,dtype=float)
    common=.10*np.sin(t/9); cs=60+np.cumsum(common+.03*np.sin(t/5)); js=55+np.cumsum(common-.02*np.sin(t/6))
    ct=4+.001*np.sin(t/11); jt=4.1+.001*np.cos(t/13)
    return pd.DataFrame({
        "date":dates,
        "CITI_representative_price":98-.01*t,"JPM_representative_price":94-.008*t,
        "CITI_displayed_volume":1_000_000+100_000*(1+np.sin(t/7)),
        "JPM_displayed_volume":1_200_000+120_000*(1+np.cos(t/8)),
        "CITI_ytc_pct":ct+cs/100,"JPM_ytc_pct":jt+js/100,
        "CITI_duration_to_call":2.4,"JPM_duration_to_call":2.9,
        "CITI_treasury_yield_pct":ct,"JPM_treasury_yield_pct":jt,
        "CITI_treasury_spread_bp":cs,"JPM_treasury_spread_bp":js,
        "pair_spread_bp":cs-js,"hist_z":np.linspace(-1.5,-1.0,n),
    })

def test_factor_identity_reconciles():
    x=add_factor_decomposition(make_test_panel(),regression_window=80,min_regression_observations=40)
    r=x.iloc[-1]
    for i in ("CITI","JPM"):
        rhs=r[f"{i}_d_treasury_bp"]+r[f"{i}_systematic_credit_bp"]+r[f"{i}_liquidity_contribution_bp"]+r[f"{i}_idiosyncratic_credit_bp"]
        assert abs(r[f"{i}_d_ytc_bp"]-rhs)<1e-8

def test_risk_snapshot_has_dv01_cs01():
    x=add_factor_decomposition(make_test_panel(),regression_window=80,min_regression_observations=40)
    r=build_cob_risk_snapshot(x)
    assert (r.dv01_usd_per_bp>0).all() and (r.cs01_usd_per_bp>0).all()

def test_pair_hedge_is_dv01_neutral():
    x=add_factor_decomposition(make_test_panel(),regression_window=80,min_regression_observations=40)
    r=build_cob_risk_snapshot(x)
    p=build_pair_risk_summary(x,r).iloc[0]
    assert abs(p.net_dv01_usd_per_bp)<1e-8
