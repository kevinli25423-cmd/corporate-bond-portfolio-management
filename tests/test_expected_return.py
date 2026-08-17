from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from corporate_bond_pm.expected_return import expected_return_from_rv


def test_expected_return_math():
    out = expected_return_from_rv(4, 3.2, 35, 3, 4, 0.75)
    assert abs(out["expected_spread_move_bp"] + 3) < 1e-12
    assert abs(out["convergence_return_bp"] - 9.6) < 1e-12
    assert abs(out["expected_return_1m_bp"] - 43.6) < 1e-12
