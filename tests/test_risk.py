from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from corporate_bond_pm.risk import bond_dv01, bond_cs01


def test_dollar_sensitivities():
    assert bond_dv01(20_000_000, 4.0) == 8_000
    assert bond_cs01(20_000_000, 3.2) == 6_400
