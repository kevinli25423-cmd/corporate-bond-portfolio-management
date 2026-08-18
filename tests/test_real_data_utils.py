from datetime import date
import pandas as pd
import pytest
from corporate_bond_pm.bond_math import FixedToFloatBond, clean_price_from_ytc, yield_to_call_from_clean_price
from corporate_bond_pm.treasury_real import interpolate_curve_row


def test_par_price_returns_coupon_yield_on_issue_date():
    bond = FixedToFloatBond("JPMorgan Chase & Co.", "46647PEU6", 0.04915, date(2025,1,24), date(2028,1,24), date(2029,1,24))
    assert clean_price_from_ytc(bond, date(2025,1,24), 0.04915) == pytest.approx(100.0, abs=1e-8)
    assert yield_to_call_from_clean_price(bond, date(2025,1,24), 100.0) == pytest.approx(0.04915, abs=1e-10)


def test_treasury_interpolation():
    row = pd.Series({1.0: 4.0, 2.0: 4.2, 3.0: 4.4, 5.0: 4.8})
    assert interpolate_curve_row(row, 2.5) == pytest.approx(4.3)
