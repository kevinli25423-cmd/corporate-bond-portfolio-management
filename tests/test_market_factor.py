import pandas as pd
import pytest

from corporate_bond_pm.market_factor import attach_ig_systematic_factor


def test_ig_factor_change_is_aligned_to_pair_dates():
    panel = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"]),
        "x": [1, 2, 3],
    })
    factor = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"]),
        "ig_oas_pct": [0.80, 0.82, 0.81],
    })
    out = attach_ig_systematic_factor(panel, factor)
    assert out.loc[1, "systematic_credit_factor_change_bp"] == pytest.approx(2.0)
    assert out.loc[2, "systematic_credit_factor_change_bp"] == pytest.approx(-1.0)
