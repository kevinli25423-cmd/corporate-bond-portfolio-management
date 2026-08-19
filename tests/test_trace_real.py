import pandas as pd
from corporate_bond_pm.trace_real import daily_trade_summary


def test_daily_trace_summary_uses_median_by_default():
    trades = pd.DataFrame({"date": pd.to_datetime(["2026-01-02"]*3), "price": [99.0,100.0,105.0], "displayed_volume": [1_000_000.0,2_000_000.0,100_000.0]})
    out = daily_trade_summary(trades, representative="median")
    assert out.loc[0,"representative_price"] == 100.0
    assert out.loc[0,"trade_count"] == 3


def test_capped_volume_preserves_lower_bound_flag(tmp_path):
    p = tmp_path / "finra.csv"
    pd.DataFrame({"Date": ["2026-01-02"], "Price": [99.5], "Quantity": ["5MM+"]}).to_csv(p, index=False)
    from corporate_bond_pm.trace_real import load_finra_trade_export
    out = load_finra_trade_export(p)
    assert out.loc[0, "displayed_volume"] == 5_000_000.0
    assert bool(out.loc[0, "volume_is_capped"]) is True


def test_last_sale_mode():
    trades = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-02"] * 3),
        "price": [99.0, 100.0, 101.5],
        "displayed_volume": [1_000_000.0, 2_000_000.0, 100_000.0],
        "source_row": [0, 1, 2],
        "volume_is_capped": [False, False, False],
    })
    out = daily_trade_summary(trades, representative="last_sale")
    assert out.loc[0, "representative_price"] == 101.5
