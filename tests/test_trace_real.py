import pandas as pd
from corporate_bond_pm.trace_real import daily_trade_summary


def test_daily_trace_summary_uses_median_by_default():
    trades = pd.DataFrame({"date": pd.to_datetime(["2026-01-02"]*3), "price": [99.0,100.0,105.0], "displayed_volume": [1_000_000.0,2_000_000.0,100_000.0]})
    out = daily_trade_summary(trades, representative="median")
    assert out.loc[0,"representative_price"] == 100.0
    assert out.loc[0,"trade_count"] == 3
