from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
REAL = ROOT / "data" / "processed" / "real"
RESULT = ROOT / "docs" / "results" / "real"

st.set_page_config(page_title="Real CITI / JPM Relative Value", layout="wide")
st.title("Real CITI / JPM Relative-Value Dashboard")
st.caption("Local FINRA observations + official U.S. Treasury curve; raw FINRA files remain local")

required = [
    REAL / "citi_jpm_real_pair_daily.csv",
    RESULT / "citi_jpm_latest.csv",
    RESULT / "citi_jpm_signal_summary.csv",
    RESULT / "citi_jpm_event_summary.csv",
]
missing = [p for p in required if not p.exists()]
if missing:
    st.warning("Run `python scripts/build_real_citi_jpm_pair.py` first.")
    st.stop()

pair = pd.read_csv(REAL / "citi_jpm_real_pair_daily.csv", parse_dates=["date"])
latest = pd.read_csv(RESULT / "citi_jpm_latest.csv").iloc[0]
signal = pd.read_csv(RESULT / "citi_jpm_signal_summary.csv")
events = pd.read_csv(RESULT / "citi_jpm_event_summary.csv")

cols = st.columns(6)
metrics = [
    ("As of", str(latest["as_of"])),
    ("CITI YTC−Treasury", f"{latest['citi_treasury_spread_bp']:.2f} bp"),
    ("JPM YTC−Treasury", f"{latest['jpm_treasury_spread_bp']:.2f} bp"),
    ("CITI − JPM", f"{latest['pair_spread_bp']:.2f} bp"),
    ("Lagged z-score", f"{latest['hist_z']:.2f}σ"),
    ("PM decision", str(latest["pm_decision"])),
]
for c, (label, value) in zip(cols, metrics):
    c.metric(label, value)

st.info(
    f"Raw signal: **{latest['raw_signal']}** · Mean-reversion direction: **{latest['mean_reversion_direction']}** · "
    f"Validation: **{latest['validation_status']}** → PM decision: **{latest['pm_decision']}**\n\n"
    f"{latest['validation_reason']}"
)

st.subheader("YTC−Treasury spreads")
st.line_chart(pair.set_index("date")[["CITI_treasury_spread_bp", "JPM_treasury_spread_bp"]])

c1, c2 = st.columns(2)
with c1:
    st.subheader("CITI − JPM spread differential")
    st.line_chart(pair.set_index("date")[["pair_spread_bp", "hist_mean_bp"]])
with c2:
    st.subheader("Lagged 252-observation z-score")
    st.line_chart(pair.set_index("date")[["hist_z"]])

st.subheader("5 / 20 / 60 observation signal-day validation")
st.dataframe(signal, use_container_width=True)

st.subheader("Independent event backtest")
st.dataframe(events, use_container_width=True)

st.caption("Spread = yield to first par call − interpolated Treasury yield. This is not OAS. Raw z-score direction is gated by historical validation before a portfolio decision is made.")
