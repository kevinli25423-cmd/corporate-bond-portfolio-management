from __future__ import annotations

from html import escape
from pathlib import Path
import math

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
RESULTS = DOCS / "results"
OUTPUT = ROOT / "data" / "output"
FIGURES = DOCS / "figures"


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def fmt(value, digits=2, suffix="") -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    try:
        return f"{float(value):,.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return escape(str(value))


def pct(value, digits=1) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return f"{float(value) * 100:.{digits}f}%"


def action_class(action: str) -> str:
    a = str(action).lower()
    if "add" in a or "buy" in a:
        return "positive"
    if "reduce" in a or "sell" in a:
        return "negative"
    return "neutral"


def signed(value: float, digits=2, suffix="") -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.{digits}f}{suffix}"


def bar(value: float, max_abs: float, cls: str = "") -> str:
    if max_abs <= 0:
        width = 0
    else:
        width = min(abs(float(value)) / max_abs * 100, 100)
    sign_cls = "pos" if float(value) >= 0 else "neg"
    return f'<div class="bar-track"><div class="bar-fill {sign_cls} {cls}" style="width:{width:.1f}%"></div></div>'


def build() -> str:
    case = read_csv(RESULTS / "bac_jpm_case_summary.csv")
    signal = read_csv(RESULTS / "bac_jpm_signal_summary.csv")
    events = read_csv(RESULTS / "bac_jpm_event_summary.csv")
    stress_case = read_csv(RESULTS / "bac_jpm_stress_comparison.csv")
    rv = read_csv(OUTPUT / "rv_dashboard.csv")
    portfolio = read_csv(OUTPUT / "portfolio_optimizer.csv")
    stress = read_csv(OUTPUT / "stress_results.csv")
    risk = read_csv(OUTPUT / "risk_dashboard.csv")

    if case.empty:
        raise FileNotFoundError(
            "Missing docs/results/bac_jpm_case_summary.csv. Run scripts/build_research_outputs.py first."
        )

    c = case.iloc[0]
    as_of = str(c.get("as_of", ""))

    kpis = [
        ("BAC OAS", fmt(c.get("bac_oas_bp"), 2, " bp"), "Current representative spread"),
        ("JPM OAS", fmt(c.get("jpm_oas_bp"), 2, " bp"), "Current representative spread"),
        ("Pair differential", fmt(c.get("market_diff_bp"), 2, " bp"), "BAC minus JPM"),
        ("Historical z-score", signed(c.get("historical_z"), 2, "σ"), "Lagged historical benchmark"),
        ("Blended RV", signed(c.get("blended_rv_bp"), 2, " bp"), "Residual spread compensation"),
        ("Expected 1M return", fmt(c.get("expected_return_1m_bp"), 2, " bp"), "Synthetic model estimate"),
    ]

    kpi_html = "".join(
        f"""
        <div class="kpi-card">
          <div class="kpi-label">{escape(label)}</div>
          <div class="kpi-value">{escape(value)}</div>
          <div class="kpi-note">{escape(note)}</div>
        </div>
        """
        for label, value, note in kpis
    )

    if not rv.empty:
        rv_rows = []
        for _, r in rv.iterrows():
            rv_rows.append(
                f"""
                <tr>
                  <td><strong>{escape(str(r['asset']))}</strong></td>
                  <td>{escape(str(r.get('credit_view', '')))}</td>
                  <td class="num">{fmt(r.get('oas_bp'), 2)}</td>
                  <td class="num">{signed(r.get('hist_pair_z'), 2)}</td>
                  <td class="num">{signed(r.get('blended_rv_bp'), 2)}</td>
                  <td class="num">{fmt(r.get('expected_return_1m_bp'), 2)}</td>
                  <td><span class="pill {action_class(r.get('action', ''))}">{escape(str(r.get('action', '')))}</span></td>
                </tr>
                """
            )
        rv_table = "".join(rv_rows)
    else:
        rv_table = '<tr><td colspan="7" class="muted">Run the portfolio pipeline to populate the issuer dashboard.</td></tr>'

    portfolio_html = ""
    if not portfolio.empty:
        max_weight = max(float(portfolio["current_weight"].max()), float(portfolio["optimizer_weight"].max()), 0.01)
        rows = []
        for _, r in portfolio.iterrows():
            asset = escape(str(r["asset"]))
            cur = float(r["current_weight"])
            opt = float(r["optimizer_weight"])
            change = float(r["weight_change"])
            rows.append(
                f"""
                <div class="allocation-row">
                  <div class="allocation-label">{asset}</div>
                  <div class="allocation-bars">
                    <div class="allocation-line"><span>Current</span>{bar(cur, max_weight, 'current')}<b>{pct(cur)}</b></div>
                    <div class="allocation-line"><span>Model</span>{bar(opt, max_weight, 'model')}<b>{pct(opt)}</b></div>
                  </div>
                  <div class="allocation-change {'up' if change >= 0 else 'down'}">{signed(change * 100, 1, ' pp')}</div>
                </div>
                """
            )
        portfolio_html = "".join(rows)
    else:
        portfolio_html = '<div class="muted">Run the portfolio pipeline to populate allocation results.</div>'

    stress_html = ""
    stress_source = stress if not stress.empty else stress_case
    if not stress_source.empty:
        pivot = stress_source.pivot(index="portfolio", columns="scenario", values="portfolio_return_pct")
        order = [x for x in ["Current", "Optimizer", "Final", "Proposed"] if x in pivot.index]
        if not order:
            order = list(pivot.index)
        rows = []
        for portfolio_name in order:
            vals = pivot.loc[portfolio_name]
            normal = vals.get("Normal", float("nan"))
            slowdown = vals.get("Slowdown", float("nan"))
            crisis = vals.get("Crisis", float("nan"))
            rows.append(
                f"""
                <tr>
                  <td><strong>{escape(str(portfolio_name))}</strong></td>
                  <td class="num {'good' if normal >= 0 else 'bad'}">{signed(normal, 2, '%')}</td>
                  <td class="num {'good' if slowdown >= 0 else 'bad'}">{signed(slowdown, 2, '%')}</td>
                  <td class="num {'good' if crisis >= 0 else 'bad'}">{signed(crisis, 2, '%')}</td>
                </tr>
                """
            )
        stress_html = "".join(rows)

    signal_rows = []
    if not signal.empty:
        for _, r in signal.iterrows():
            signal_rows.append(
                f"""
                <tr>
                  <td>{int(r['horizon_days'])}D</td>
                  <td class="num">{int(r['observations'])}</td>
                  <td class="num">{fmt(r['avg_signed_convergence_bp'], 2, ' bp')}</td>
                  <td class="num">{pct(r['convergence_hit_rate'])}</td>
                  <td class="num">{fmt(r['avg_gross_pair_return_bp'], 2, ' bp')}</td>
                  <td class="num">{fmt(r['avg_clipped_convergence_ratio'], 2)}</td>
                </tr>
                """
            )
    signal_table = "".join(signal_rows)

    if not events.empty:
        e = events.iloc[0]
        event_cards = f"""
          <div class="mini-stat"><span>Independent events</span><b>{int(e['events'])}</b></div>
          <div class="mini-stat"><span>Gross hit rate</span><b>{pct(e['gross_hit_rate'])}</b></div>
          <div class="mini-stat"><span>Avg net pair return</span><b>{fmt(e['avg_net_pair_return_bp'], 2, ' bp')}</b></div>
          <div class="mini-stat"><span>Net-positive rate</span><b>{pct(e['net_positive_rate'])}</b></div>
          <div class="mini-stat"><span>Clipped convergence ratio</span><b>{fmt(e['avg_clipped_convergence_ratio'], 2)}</b></div>
          <div class="mini-stat"><span>Pair cost assumption</span><b>{fmt(e['pair_transaction_cost_bp'], 1, ' bp')}</b></div>
        """
    else:
        event_cards = '<div class="muted">Event summary unavailable.</div>'

    if not risk.empty:
        total_dv01 = risk["dv01"].sum()
        total_cs01 = risk["cs01"].sum()
        top_issuer = risk.loc[risk["cs01"].idxmax(), "issuer"] if len(risk) else "—"
        risk_cards = f"""
          <div class="mini-stat"><span>Portfolio DV01</span><b>${total_dv01:,.0f}/bp</b></div>
          <div class="mini-stat"><span>Portfolio CS01</span><b>${total_cs01:,.0f}/bp</b></div>
          <div class="mini-stat"><span>Largest CS01 contributor</span><b>{escape(str(top_issuer))}</b></div>
        """
    else:
        risk_cards = '<div class="muted">Risk dashboard unavailable until the pipeline is run.</div>'

    action = escape(str(c.get("model_action", "")))
    historical_z = float(c.get("historical_z", 0))
    blended_rv = float(c.get("blended_rv_bp", 0))

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Corporate Bond Portfolio Research Dashboard</title>
<style>
:root {{
  --bg:#07111f; --panel:#0d1b2a; --panel2:#11263b; --text:#edf3f9; --muted:#94a9bd;
  --line:#20364b; --accent:#4db5ff; --accent2:#9b8cff; --green:#2dd4a8; --red:#ff6b7d; --amber:#f5c451;
}}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Arial,sans-serif; background:linear-gradient(180deg,#06101c 0%,#081522 100%); color:var(--text); }}
a {{ color:#75c9ff; text-decoration:none; }} a:hover {{ text-decoration:underline; }}
.container {{ width:min(1180px,calc(100% - 32px)); margin:0 auto; }}
.topbar {{ position:sticky; top:0; z-index:20; backdrop-filter:blur(18px); background:rgba(7,17,31,.84); border-bottom:1px solid var(--line); }}
.nav {{ height:58px; display:flex; align-items:center; justify-content:space-between; gap:18px; }}
.brand {{ font-weight:750; letter-spacing:.1px; }}
.navlinks {{ display:flex; gap:16px; flex-wrap:wrap; font-size:13px; }}
.hero {{ padding:70px 0 34px; }}
.eyebrow {{ color:var(--accent); text-transform:uppercase; letter-spacing:.14em; font-size:12px; font-weight:800; }}
h1 {{ font-size:clamp(36px,5vw,62px); line-height:1.02; margin:10px 0 18px; max-width:900px; }}
.hero p {{ max-width:800px; color:var(--muted); font-size:18px; line-height:1.65; }}
.badges {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:20px; }}
.badge {{ padding:7px 10px; border:1px solid var(--line); border-radius:999px; background:rgba(255,255,255,.03); color:#c8d6e3; font-size:12px; }}
.kpi-grid {{ display:grid; grid-template-columns:repeat(6,1fr); gap:12px; margin:22px 0 34px; }}
.kpi-card {{ background:linear-gradient(145deg,rgba(17,38,59,.96),rgba(10,25,40,.96)); border:1px solid var(--line); border-radius:16px; padding:18px; min-height:128px; box-shadow:0 10px 28px rgba(0,0,0,.18); }}
.kpi-label {{ font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.07em; }}
.kpi-value {{ font-size:27px; font-weight:800; margin:11px 0 7px; }}
.kpi-note {{ font-size:12px; color:#7890a6; line-height:1.35; }}
.section {{ padding:28px 0 16px; scroll-margin-top:70px; }}
.section-head {{ display:flex; justify-content:space-between; align-items:end; gap:16px; margin-bottom:14px; }}
h2 {{ font-size:27px; margin:0; }}
.section-sub {{ color:var(--muted); font-size:14px; max-width:720px; line-height:1.55; }}
.grid-2 {{ display:grid; grid-template-columns:1.15fr .85fr; gap:16px; }}
.panel {{ background:rgba(13,27,42,.88); border:1px solid var(--line); border-radius:18px; padding:20px; box-shadow:0 12px 34px rgba(0,0,0,.16); }}
.panel h3 {{ margin:0 0 14px; font-size:17px; }}
.decision {{ background:linear-gradient(120deg,rgba(77,181,255,.12),rgba(155,140,255,.10)); border:1px solid rgba(77,181,255,.38); }}
.decision-title {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
.decision-title strong {{ font-size:22px; }}
.decision p {{ color:#b7c7d7; line-height:1.6; }}
.pill {{ display:inline-flex; align-items:center; padding:5px 9px; border-radius:999px; font-size:12px; font-weight:750; }}
.pill.positive {{ color:#73efd0; background:rgba(45,212,168,.11); border:1px solid rgba(45,212,168,.28); }}
.pill.negative {{ color:#ff98a4; background:rgba(255,107,125,.10); border:1px solid rgba(255,107,125,.25); }}
.pill.neutral {{ color:#f3d98a; background:rgba(245,196,81,.10); border:1px solid rgba(245,196,81,.22); }}
.table-wrap {{ overflow:auto; }}
table {{ width:100%; border-collapse:collapse; min-width:640px; }}
th {{ text-align:left; color:#8fa5b9; font-size:11px; text-transform:uppercase; letter-spacing:.07em; padding:10px 10px; border-bottom:1px solid var(--line); }}
td {{ padding:12px 10px; border-bottom:1px solid rgba(32,54,75,.65); color:#d9e4ee; font-size:13px; }}
tr:last-child td {{ border-bottom:0; }}
.num {{ font-variant-numeric:tabular-nums; text-align:right; }}
.good {{ color:#73efd0; }} .bad {{ color:#ff93a0; }} .muted {{ color:var(--muted); }}
.figure {{ overflow:hidden; padding:0; }}
.figure img {{ width:100%; height:auto; display:block; background:white; }}
.figure-caption {{ padding:12px 16px; color:var(--muted); font-size:12px; }}
.allocation-row {{ display:grid; grid-template-columns:60px 1fr 72px; gap:12px; align-items:center; padding:10px 0; border-bottom:1px solid rgba(32,54,75,.55); }}
.allocation-row:last-child {{ border-bottom:0; }}
.allocation-label {{ font-weight:750; }}
.allocation-bars {{ display:grid; gap:5px; }}
.allocation-line {{ display:grid; grid-template-columns:52px 1fr 48px; gap:8px; align-items:center; color:var(--muted); font-size:11px; }}
.allocation-line b {{ color:#dce7f0; font-weight:650; text-align:right; }}
.bar-track {{ height:8px; border-radius:99px; background:#172a3d; overflow:hidden; }}
.bar-fill {{ height:100%; border-radius:99px; background:var(--accent); }}
.bar-fill.model {{ background:var(--accent2); }}
.allocation-change {{ text-align:right; font-weight:750; font-size:12px; }}
.allocation-change.up {{ color:#6be7c7; }} .allocation-change.down {{ color:#ff8e9a; }}
.mini-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }}
.mini-stat {{ border:1px solid var(--line); border-radius:12px; padding:13px; background:rgba(255,255,255,.018); }}
.mini-stat span {{ display:block; color:var(--muted); font-size:11px; margin-bottom:7px; }}
.mini-stat b {{ font-size:17px; }}
.insight-list {{ margin:0; padding-left:18px; color:#b9c9d7; line-height:1.65; }}
.links {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }}
.link-card {{ display:block; padding:16px; border:1px solid var(--line); border-radius:13px; background:rgba(255,255,255,.018); color:var(--text); }}
.link-card small {{ display:block; color:var(--muted); margin-top:7px; line-height:1.4; }}
footer {{ margin-top:40px; border-top:1px solid var(--line); padding:28px 0 50px; color:#7890a6; font-size:12px; line-height:1.55; }}
@media (max-width:1000px) {{ .kpi-grid {{ grid-template-columns:repeat(3,1fr); }} .grid-2 {{ grid-template-columns:1fr; }} .links {{ grid-template-columns:repeat(2,1fr); }} }}
@media (max-width:640px) {{ .container {{ width:min(100% - 20px,1180px); }} .hero {{ padding-top:48px; }} .kpi-grid {{ grid-template-columns:repeat(2,1fr); }} .navlinks {{ display:none; }} .mini-grid {{ grid-template-columns:repeat(2,1fr); }} .links {{ grid-template-columns:1fr; }} .allocation-row {{ grid-template-columns:52px 1fr; }} .allocation-change {{ grid-column:2; }} }}
</style>
</head>
<body>
<div class="topbar">
  <div class="container nav">
    <div class="brand">Corporate Bond PM Research</div>
    <div class="navlinks">
      <a href="#rv">Relative Value</a><a href="#portfolio">Portfolio</a><a href="#stress">Stress</a><a href="#validation">Validation</a><a href="#research">Research Notes</a>
    </div>
  </div>
</div>

<main class="container">
<section class="hero">
  <div class="eyebrow">Institutional fixed-income research dashboard</div>
  <h1>Corporate Bond Portfolio Management</h1>
  <p>A reproducible synthetic research framework connecting credit analysis, relative value, risk decomposition, expected return, portfolio construction, stress testing, trading, attribution, and chronological validation.</p>
  <div class="badges"><span class="badge">Synthetic research data</span><span class="badge">As of {escape(as_of)}</span><span class="badge">$100M Financials sleeve</span><span class="badge">Python research pipeline</span></div>
</section>

<section>
  <div class="kpi-grid">{kpi_html}</div>
</section>

<section class="section" id="rv">
  <div class="section-head"><div><h2>Relative value</h2><div class="section-sub">The signal asks whether observed spread compensation remains attractive after credit, bond characteristics, liquidity, and a regression confirmation layer.</div></div></div>
  <div class="grid-2">
    <div class="panel decision">
      <div class="decision-title"><span class="pill positive">Model action</span><strong>{action}</strong></div>
      <p>BAC trades {fmt(c.get('market_diff_bp'),2,' bp')} wider than JPM in the representative synthetic pair. The lagged historical z-score is {signed(historical_z,2,'σ')} and the blended unexplained spread component is {signed(blended_rv,2,' bp')}. The signal supports a moderate relative overweight, but position size remains constrained by concentration and stress loss.</p>
      <div class="mini-grid">
        <div class="mini-stat"><span>Historical mean pair spread</span><b>{fmt(c.get('historical_mean_diff_bp'),2,' bp')}</b></div>
        <div class="mini-stat"><span>CDS differential</span><b>{fmt(c.get('cds_diff_bp'),2,' bp')}</b></div>
        <div class="mini-stat"><span>Fair differential</span><b>{fmt(c.get('fair_diff_bp'),2,' bp')}</b></div>
        <div class="mini-stat"><span>CDS / bond RV</span><b>{signed(c.get('cds_bond_rv_bp'),2,' bp')}</b></div>
        <div class="mini-stat"><span>Regression RV</span><b>{signed(c.get('regression_rv_bp'),2,' bp')}</b></div>
        <div class="mini-stat"><span>Blended RV</span><b>{signed(c.get('blended_rv_bp'),2,' bp')}</b></div>
      </div>
    </div>
    <div class="panel figure"><img src="figures/bac_jpm_rv_decomposition.png" alt="BAC JPM RV decomposition"><div class="figure-caption">BAC/JPM relative-value decomposition.</div></div>
  </div>

  <div class="panel" style="margin-top:16px">
    <h3>Issuer dashboard</h3>
    <div class="table-wrap"><table><thead><tr><th>Asset</th><th>Credit view</th><th class="num">OAS bp</th><th class="num">Hist z</th><th class="num">Blended RV bp</th><th class="num">Expected 1M bp</th><th>Action</th></tr></thead><tbody>{rv_table}</tbody></table></div>
  </div>

  <div class="grid-2" style="margin-top:16px">
    <div class="panel figure"><img src="figures/bac_jpm_pair_spread.png" alt="BAC JPM pair spread"><div class="figure-caption">Observed BAC-JPM spread differential through time.</div></div>
    <div class="panel figure"><img src="figures/bac_jpm_zscore.png" alt="BAC JPM z score"><div class="figure-caption">Lagged historical z-score used for the relative-value signal.</div></div>
  </div>
</section>

<section class="section" id="portfolio">
  <div class="section-head"><div><h2>Portfolio construction</h2><div class="section-sub">Expected return is translated into allocation subject to duration, liquidity, cash, and concentration constraints. The optimizer is a decision-support layer rather than an automatic portfolio rule.</div></div></div>
  <div class="grid-2">
    <div class="panel"><h3>Current vs model allocation</h3>{portfolio_html}</div>
    <div class="panel"><h3>Risk snapshot</h3><div class="mini-grid">{risk_cards}</div><ul class="insight-list" style="margin-top:16px"><li>Allocation changes are evaluated together with issuer CS01 and stress loss.</li><li>Cash remains an explicit portfolio asset and liquidity buffer.</li><li>Relative-value alpha is not allowed to override risk-budget constraints.</li></ul></div>
  </div>
</section>

<section class="section" id="stress">
  <div class="section-head"><div><h2>Stress testing</h2><div class="section-sub">Scenario analysis asks whether incremental spread compensation is sufficient relative to downside risk rather than attempting to predict the timing of a crisis.</div></div></div>
  <div class="grid-2">
    <div class="panel"><h3>Scenario returns</h3><div class="table-wrap"><table><thead><tr><th>Portfolio</th><th class="num">Normal</th><th class="num">Slowdown</th><th class="num">Crisis</th></tr></thead><tbody>{stress_html}</tbody></table></div></div>
    <div class="panel figure"><img src="figures/bac_jpm_stress_comparison.png" alt="Stress comparison"><div class="figure-caption">Current vs proposed BAC/JPM trade stress comparison.</div></div>
  </div>
</section>

<section class="section" id="validation">
  <div class="section-head"><div><h2>Chronological validation</h2><div class="section-sub">Signal quality is evaluated using future pair-spread changes only. Historical means and z-scores are lagged, and an independent-event test blocks overlapping entries.</div></div></div>
  <div class="panel">
    <h3>Forward convergence by horizon</h3>
    <div class="table-wrap"><table><thead><tr><th>Horizon</th><th class="num">Signals</th><th class="num">Avg convergence</th><th class="num">Hit rate</th><th class="num">Avg gross pair return</th><th class="num">Clipped q</th></tr></thead><tbody>{signal_table}</tbody></table></div>
  </div>
  <div class="mini-grid" style="margin-top:16px">{event_cards}</div>
  <div class="grid-2" style="margin-top:16px">
    <div class="panel figure"><img src="figures/bac_jpm_backtest_horizon_summary.png" alt="Backtest horizon summary"><div class="figure-caption">Convergence and pair-return behavior across forward horizons.</div></div>
    <div class="panel figure"><img src="figures/bac_jpm_event_returns_20d.png" alt="Independent event returns"><div class="figure-caption">Non-overlapping 20-business-day event returns after an explicit transaction-cost assumption.</div></div>
  </div>
</section>

<section class="section" id="research">
  <div class="section-head"><div><h2>Research notes</h2><div class="section-sub">Detailed methodology, data definitions, calculations, and validation assumptions are kept alongside the reproducible code.</div></div></div>
  <div class="links">
    <a class="link-card" href="bac_jpm_case_study.md"><strong>BAC / JPM case study</strong><small>End-to-end relative-value thesis, trade sizing, and stress interpretation.</small></a>
    <a class="link-card" href="bac_jpm_backtest.md"><strong>RV validation</strong><small>Chronological signal outcomes and non-overlapping event backtest.</small></a>
    <a class="link-card" href="methodology.md"><strong>Methodology</strong><small>Model architecture, assumptions, formulas, and portfolio process.</small></a>
    <a class="link-card" href="data_contract.md"><strong>Data contract</strong><small>Security master, market, fundamental, CDS, and liquidity schemas.</small></a>
  </div>
</section>

<footer>
  <strong>Research disclaimer.</strong> This dashboard is an independent personal research and educational project. The dataset and portfolio results are synthetic and illustrative. They are not live market quotations, investment advice, proprietary institutional data, or actual portfolio holdings.
</footer>
</main>
</body>
</html>"""
    return html


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    out = DOCS / "index.html"
    out.write_text(build(), encoding="utf-8")
    (DOCS / ".nojekyll").touch()
    print(f"Static research dashboard written to {out}")


if __name__ == "__main__":
    main()
