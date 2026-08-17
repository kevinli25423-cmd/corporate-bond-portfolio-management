from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from corporate_bond_pm.relative_value import fair_pair_differential, historical_pair_signal


def test_fair_pair_math():
    out = fair_pair_differential(80, 68, 58, 52, duration_adj_bp=1, liquidity_adj_bp=1)
    assert out["market_diff_bp"] == 12
    assert out["fair_diff_bp"] == 8
    assert out["rv_residual_bp"] == 4


def test_historical_signal_is_lagged():
    dates = pd.bdate_range("2025-01-01", periods=70)
    a = pd.DataFrame({"date": dates, "security_id": "A", "oas_bp": range(70)})
    b = pd.DataFrame({"date": dates, "security_id": "B", "oas_bp": [0] * 70})
    out = historical_pair_signal(pd.concat([a, b]), "A", "B", window=60, min_history=60)
    row = out.iloc[60]
    assert abs(row["hist_mean_bp"] - 29.5) < 1e-9
