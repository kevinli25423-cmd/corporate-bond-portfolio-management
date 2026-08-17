from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "output"

st.set_page_config(page_title="Corporate Bond Portfolio Dashboard", layout="wide")
st.title("Institutional Corporate Bond Portfolio Dashboard")
st.caption("Independent research prototype using synthetic demonstration data")

required = [
    "rv_dashboard.csv",
    "portfolio_optimizer.csv",
    "stress_results.csv",
    "trade_blotter.csv",
    "attribution.csv",
]
missing = [name for name in required if not (OUT / name).exists()]
if missing:
    st.warning("Run `python scripts/generate_demo_data.py` and `python scripts/run_pipeline.py` first.")
    st.stop()

rv = pd.read_csv(OUT / "rv_dashboard.csv")
opt = pd.read_csv(OUT / "portfolio_optimizer.csv")
stress = pd.read_csv(OUT / "stress_results.csv")
blotter = pd.read_csv(OUT / "trade_blotter.csv")
attribution = pd.read_csv(OUT / "attribution.csv")

st.subheader("Relative Value & Expected Return")
st.dataframe(
    rv[[
        "asset", "credit_view", "oas_bp", "cds_5y_bp", "hist_pair_z",
        "cds_bond_rv_bp", "regression_rv_bp", "blended_rv_bp",
        "expected_return_1m_bp", "action",
    ]],
    use_container_width=True,
)

c1, c2 = st.columns(2)
with c1:
    st.subheader("Current vs Optimizer Weights")
    st.bar_chart(opt.set_index("asset")[["current_weight", "optimizer_weight"]])
with c2:
    st.subheader("Stress Results")
    st.dataframe(
        stress.pivot(index="scenario", columns="portfolio", values="portfolio_return_pct").round(2),
        use_container_width=True,
    )

st.subheader("Trade Blotter")
st.dataframe(blotter, use_container_width=True)

st.subheader("One-Month Attribution")
st.bar_chart(attribution.set_index("driver")["pnl"])
