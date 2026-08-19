import pandas as pd
from scripts.build_real_citi_jpm_pair import standard_tplus1_settlement


def test_tplus1_skips_weekend():
    assert standard_tplus1_settlement(pd.Timestamp("2026-08-14")) == pd.Timestamp("2026-08-17")


def test_tplus1_skips_us_federal_holiday():
    # Friday July 3, 2026 is the observed Independence Day holiday.
    assert standard_tplus1_settlement(pd.Timestamp("2026-07-02")) == pd.Timestamp("2026-07-06")
