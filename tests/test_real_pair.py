import pandas as pd

from corporate_bond_pm.real_pair import (
    add_forward_validation,
    add_lagged_zscore,
    assess_validation,
    classify_signal,
)


def test_lagged_zscore_does_not_use_current_observation():
    x = pd.DataFrame({"pair_spread_bp": [1.0, 2.0, 3.0, 100.0]})
    out = add_lagged_zscore(x, window=3)
    assert out.loc[3, "hist_mean_bp"] == 2.0
    assert out.loc[3, "hist_std_bp"] == 1.0
    assert out.loc[3, "hist_z"] == 98.0


def test_forward_validation_is_future_only():
    x = pd.DataFrame({
        "pair_spread_bp": [10.0, 8.0, 7.0],
        "hist_mean_bp": [0.0, 0.0, 0.0],
        "hist_z": [2.0, 1.5, 1.0],
        "matched_duration": [4.0, 4.0, 4.0],
    })
    out = add_forward_validation(x, horizons=[1])
    assert out.loc[0, "signed_convergence_1obs_bp"] == 2.0
    assert out.loc[0, "gross_pair_return_1obs_bp"] == 8.0


def test_signal_classification():
    assert classify_signal(0.5)[1] == "No trade"
    assert classify_signal(1.2)[1] == "Long CITI / Short JPM"
    assert classify_signal(-2.2)[1] == "Short CITI / Long JPM"


def test_validation_rejects_negative_primary_horizon():
    signal = pd.DataFrame([{
        "horizon_observations": 20,
        "observations": 63,
        "avg_gross_pair_return_bp": -3.6,
        "convergence_hit_rate": 0.38,
    }])
    events = pd.DataFrame([{
        "horizon_observations": 20,
        "events": 1,
        "avg_net_pair_return_bp": -2.7,
        "net_positive_rate": 0.0,
    }])
    status, decision, _ = assess_validation(signal, events, primary_horizon=20)
    assert status == "Not supported"
    assert decision == "No trade"
