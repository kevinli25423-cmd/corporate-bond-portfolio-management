from __future__ import annotations

from html import escape
from pathlib import Path
import json
import math

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "docs/results/real"
DOCS = ROOT / "docs"
CONFIG = ROOT / "config"


def fmt(v, digits=2, suffix=""):
    try:
        if v is None or math.isnan(float(v)):
            return "—"
        return f"{float(v):,.{digits}f}{suffix}"
    except Exception:
        return escape(str(v))


def money(v):
    try:
        return f"${float(v):,.0f}"
    except Exception:
        return "—"


def money_mm(v):
    try:
        return f"${float(v)/1_000_000:,.2f}mm"
    except Exception:
        return "—"


def pct(v):
    try:
        return f"{100.0*float(v):.1f}%"
    except Exception:
        return "—"


def load_result(name):
    path = RESULT / name
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run pair build and risk build before dashboard build."
        )
    return pd.read_csv(path)


def fmt_fundamental(value, unit):
    if pd.isna(value):
        return "—"
    if unit == "%":
        return f"{float(value):.2f}%"
    if unit == "$bn":
        return f"${float(value):,.1f}bn"
    if unit == "$tn":
        return f"${float(value):,.2f}tn"
    return f"{float(value):,.2f}"


def main():
    latest = load_result("citi_jpm_latest.csv").iloc[0]
    signal = load_result("citi_jpm_signal_summary.csv")
    events = load_result("citi_jpm_event_summary.csv")
    risk = load_result("citi_jpm_risk_snapshot.csv")
    pair = load_result("citi_jpm_pair_risk_summary.csv").iloc[0]
    krd = load_result("citi_jpm_krd_snapshot.csv")
    stress = load_result("citi_jpm_pair_stress.csv")

    f = pd.read_csv(CONFIG / "citi_jpm_fundamentals_2q26.csv")
    fsrc = json.loads((CONFIG / "citi_jpm_fundamental_sources.json").read_text())
    scenario = json.loads((CONFIG / "citi_jpm_dashboard_scenario.json").read_text())

    rmap = {r.issuer: r for r in risk.itertuples()}
    citi = rmap["CITI"]
    jpm = rmap["JPM"]

    sig20 = signal.loc[signal["horizon_observations"] == 20]
    if sig20.empty:
        gross20 = float("nan")
        conv20 = float("nan")
        hit20 = float("nan")
    else:
        gross20 = float(sig20.iloc[0]["avg_gross_pair_return_bp"])
        conv20 = float(sig20.iloc[0]["avg_signed_convergence_bp"])
        hit20 = float(sig20.iloc[0]["convergence_hit_rate"])

    cost = float(scenario["round_trip_pair_cost_bp"])
    net20 = gross20 - cost if math.isfinite(gross20) else float("nan")
    execution_gate = "Pass" if math.isfinite(net20) and net20 > 0 else "Fail"

    reference_sleeve = float(scenario["reference_sleeve_usd"])
    gross_mv_pct = abs(float(pair.gross_market_value_usd)) / reference_sleeve
    net_mv_pct = float(pair.net_market_value_usd) / reference_sleeve

    signal_rows = "".join(
        f"<tr><td>{int(r.horizon_observations)} obs</td><td>{int(r.observations)}</td>"
        f"<td>{fmt(r.avg_signed_convergence_bp,2,' bp')}</td><td>{pct(r.convergence_hit_rate)}</td>"
        f"<td>{fmt(r.avg_gross_pair_return_bp,2,' bp')}</td></tr>"
        for r in signal.itertuples()
    )
    event_rows = "".join(
        f"<tr><td>{int(r.horizon_observations)} obs</td><td>{int(r.events)}</td>"
        f"<td>{pct(r.gross_hit_rate)}</td><td>{fmt(r.avg_gross_pair_return_bp,2,' bp')}</td>"
        f"<td>{fmt(r.avg_net_pair_return_bp,2,' bp')}</td><td>{pct(r.net_positive_rate)}</td></tr>"
        for r in events.itertuples()
    )
    risk_rows = "".join(
        f"<tr><td>{r.issuer}</td><td>{fmt(r.price,3)}</td><td>{fmt(r.ytc_pct,4,'%')}</td>"
        f"<td>{fmt(r.treasury_yield_pct,4,'%')}</td><td>{fmt(r.treasury_spread_bp,2,' bp')}</td>"
        f"<td>{fmt(r.duration_to_call,3)}</td><td>{money(r.dv01_usd_per_bp)}</td>"
        f"<td>{money(r.cs01_usd_per_bp)}</td><td>{fmt(r.volume_vs_20obs_median,2,'x')}</td></tr>"
        for r in risk.itertuples()
    )
    factor_rows = "".join(
        f"<tr><td>{r.issuer}</td><td>{fmt(r.ytc_change_bp,2,' bp')}</td>"
        f"<td>{fmt(r.treasury_change_bp,2,' bp')}</td><td>{fmt(r.systematic_credit_bp,2,' bp')}</td>"
        f"<td>{fmt(r.liquidity_contribution_bp,2,' bp')}</td>"
        f"<td>{fmt(r.idiosyncratic_credit_bp,2,' bp')}</td><td>{fmt(r.spread_change_bp,2,' bp')}</td></tr>"
        for r in risk.itertuples()
    )
    pnl_rows = "".join(
        f"<tr><td>{r.issuer}</td><td>{money(r.rate_pnl_usd_long)}</td>"
        f"<td>{money(r.systematic_credit_pnl_usd_long)}</td><td>{money(r.liquidity_pnl_usd_long)}</td>"
        f"<td>{money(r.idiosyncratic_credit_pnl_usd_long)}</td><td>{money(r.factor_pnl_usd_long)}</td>"
        f"<td>{money(r.clean_price_pnl_usd_long)}</td><td>{money(r.pricing_residual_pnl_usd_long)}</td></tr>"
        for r in risk.itertuples()
    )
    stress_rows = "".join(
        f"<tr><td>{escape(str(r.scenario))}</td><td>{fmt(r.rates_bp,1,' bp')}</td>"
        f"<td>{fmt(r.common_credit_bp,1,' bp')}</td><td>{fmt(r.citi_idio_bp,1,' bp')}</td>"
        f"<td>{fmt(r.jpm_idio_bp,1,' bp')}</td><td>{fmt(r.citi_liquidity_bp,1,' bp')}</td><td>{fmt(r.jpm_liquidity_bp,1,' bp')}</td>"
        f"<td>{money(r.pair_pnl_usd)}</td></tr>"
        for r in stress.itertuples()
    )
    fundamental_rows = "".join(
        f"<tr><td>{escape(str(r.group))}</td><td>{escape(str(r.metric))}</td>"
        f"<td>{fmt_fundamental(r.CITI,r.unit)}</td><td>{fmt_fundamental(r.JPM,r.unit)}</td>"
        f"<td class='left'>{escape(str(r.note))}</td></tr>"
        for r in f.itertuples()
    )

    krd_cols = [c for c in krd.columns if c.startswith("krd_")]
    krd_header = "".join(
        f"<th>{escape(c.replace('krd_','').upper())}</th>" for c in krd_cols
    )
    krd_rows = ""
    for _, row in krd.iterrows():
        cells = "".join(f"<td>{money(row[c])}</td>" for c in krd_cols)
        krd_rows += (
            f"<tr><td>{escape(str(row['issuer']))}</td>"
            f"<td>{fmt(row['years_to_first_par_call'],2)}</td>{cells}</tr>"
        )

    # Fundamental narrative from the disclosed snapshot.
    def fv(metric, issuer):
        row = f.loc[f["metric"] == metric]
        return float(row.iloc[0][issuer]) if not row.empty else float("nan")

    cet1_gap = fv("CET1 ratio", "JPM") - fv("CET1 ratio", "CITI")
    nco_gap = fv("Net charge-off rate", "CITI") - fv("Net charge-off rate", "JPM")
    funding_ratio = fv("Total deposits", "JPM") / fv("Total deposits", "CITI")

    raw_signal = escape(str(latest.raw_signal))
    direction = escape(str(latest.mean_reversion_direction))
    validation = escape(str(latest.validation_status))
    decision = escape(str(latest.pm_decision))
    reason = escape(str(latest.validation_reason))

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CITI / JPM Corporate Bond PM Dashboard</title>
<style>
:root{{--ink:#17212b;--muted:#66727d;--line:#dfe4e8;--soft:#f5f7f8;--accent:#274c77;--accent2:#486581;--warn:#7b5b1a;}}
*{{box-sizing:border-box}}
body{{margin:0;background:#fff;color:var(--ink);font-family:Arial,Helvetica,sans-serif}}
main{{width:min(1240px,calc(100% - 34px));margin:auto;padding:42px 0 80px}}
header{{border-bottom:2px solid var(--ink);padding-bottom:20px;margin-bottom:28px}}
h1,h2{{font-family:Georgia,"Times New Roman",serif;font-weight:600}}
h1{{font-size:42px;line-height:1.08;margin:6px 0 9px}}
h2{{font-size:27px;margin:44px 0 12px}}
h3{{font-size:16px;margin:0 0 8px}}
p{{line-height:1.62;color:#37424c}}
.eyebrow{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:700}}
.subtitle{{max-width:980px;color:var(--muted);font-size:15px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}}
.kpi,.panel,.figure{{border:1px solid var(--line);background:#fff;padding:15px 16px}}
.k{{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:700}}
.v{{font-family:Georgia,"Times New Roman",serif;font-size:24px;margin-top:9px}}
.note,.caption,.small{{font-size:12px;color:var(--muted);line-height:1.5}}
.decision{{border-left:4px solid var(--accent)}}
.decisionline{{font-family:Georgia,"Times New Roman",serif;font-size:22px;margin:7px 0}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.grid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
.figure{{margin-top:14px;padding:12px}}
.figure img{{width:100%;display:block;background:#fff}}
table{{width:100%;border-collapse:collapse;background:#fff}}
th,td{{padding:9px 10px;border-bottom:1px solid var(--line);font-size:12px}}
th{{background:var(--soft);text-align:left;color:#4e5a65;font-size:10px;text-transform:uppercase;letter-spacing:.04em}}
td:not(:first-child),th:not(:first-child){{text-align:right}}
td.left{{text-align:left}}
.tablewrap{{border:1px solid var(--line);overflow-x:auto}}
.soft{{background:var(--soft)}}
.eq{{font-family:"Courier New",monospace;font-size:13px;background:#f7f8f9;border:1px solid var(--line);padding:12px;white-space:pre-line}}
.callout{{border:1px solid var(--line);background:var(--soft);padding:16px 18px;margin:14px 0}}
.source{{font-size:11px;color:var(--muted)}}
.source a{{color:var(--accent);text-decoration:none}}
.badge{{display:inline-block;border:1px solid var(--line);padding:3px 7px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;background:#fff}}
.footer{{border-top:1px solid var(--line);margin-top:44px;padding-top:18px;color:var(--muted);font-size:11px}}
@media(max-width:900px){{.kpis,.grid3{{grid-template-columns:repeat(2,1fr)}}.grid2{{grid-template-columns:1fr}}}}
@media(max-width:560px){{.kpis,.grid3{{grid-template-columns:1fr}}h1{{font-size:34px}}}}
</style>
</head>
<body>
<main>
<header>
<div class="eyebrow">Corporate Bond Portfolio Research</div>
<h1>CITI / JPM Relative-Value, Credit &amp; Portfolio Dashboard</h1>
<div class="subtitle">
CITI 172967ME8 versus JPM 46647PBE5. The workflow integrates bond pricing, fundamental credit,
relative value, close-of-business risk-factor attribution, liquidity and execution analysis,
historical validation, stress testing, and portfolio-impact sizing.
</div>
</header>

<h2>1. Executive portfolio view</h2>
<div class="kpis">
<div class="kpi"><div class="k">COB date</div><div class="v">{escape(str(latest.as_of))}</div><div class="note">Prior observation {escape(str(citi.prior_date))}</div></div>
<div class="kpi"><div class="k">CITI YTC−Treasury</div><div class="v">{fmt(latest.citi_treasury_spread_bp,2,' bp')}</div><div class="note">YTC {fmt(latest.citi_ytc_pct,4,'%')}</div></div>
<div class="kpi"><div class="k">JPM YTC−Treasury</div><div class="v">{fmt(latest.jpm_treasury_spread_bp,2,' bp')}</div><div class="note">YTC {fmt(latest.jpm_ytc_pct,4,'%')}</div></div>
<div class="kpi"><div class="k">CITI − JPM</div><div class="v">{fmt(latest.pair_spread_bp,2,' bp')}</div><div class="note">Relative spread differential</div></div>
<div class="kpi"><div class="k">Lagged z-score</div><div class="v">{fmt(latest.hist_z,2,'σ')}</div><div class="note">252-observation historical benchmark</div></div>
<div class="kpi"><div class="k">Raw RV signal</div><div class="v" style="font-size:18px">{raw_signal}</div><div class="note">{direction}</div></div>
<div class="kpi"><div class="k">Validation</div><div class="v" style="font-size:18px">{validation}</div><div class="note">20-observation primary horizon</div></div>
<div class="kpi"><div class="k">PM decision</div><div class="v" style="font-size:18px">{decision}</div><div class="note">Signal is not an automatic trade</div></div>
</div>
<div class="panel decision">
<div class="k">Investment decision</div>
<div class="decisionline">{raw_signal} · {direction} → {decision}</div>
<p>{reason}</p>
</div>

<h2>2. Investment idea</h2>
<div class="grid2">
<div class="panel">
<h3>Research question</h3>
<p>CITI and JPM are comparable large-bank senior fixed-to-floating bonds. The question is not whether their spreads are identical, but whether the observed CITI−JPM differential is large enough relative to history, fundamentals, risk and implementation cost to justify a position.</p>
</div>
<div class="panel">
<h3>Decision chain</h3>
<div class="eq">Market price → YTC → Treasury spread → Relative value
→ Fundamental credit → Risk → Liquidity / execution
→ Validation → Portfolio impact → PM decision</div>
</div>
</div>

<h2>3. Fundamental credit</h2>
<p>
The latest disclosed 2Q26 issuer fundamentals provide a credit-quality check before a relative-value signal is considered investable.
</p>
<div class="tablewrap">
<table>
<thead><tr><th>Area</th><th>Metric</th><th>CITI</th><th>JPM</th><th class="left">Definition / note</th></tr></thead>
<tbody>{fundamental_rows}</tbody>
</table>
</div>
<div class="grid3" style="margin-top:14px">
<div class="panel soft"><div class="k">Capital read-through</div><div class="v">{fmt(cet1_gap,1,' pp')}</div><div class="note">JPM CET1 advantage versus CITI.</div></div>
<div class="panel soft"><div class="k">Credit-cost read-through</div><div class="v">{fmt(nco_gap,2,' pp')}</div><div class="note">CITI net charge-off rate minus JPM.</div></div>
<div class="panel soft"><div class="k">Funding scale</div><div class="v">{fmt(funding_ratio,2,'x')}</div><div class="note">JPM deposits relative to CITI deposits.</div></div>
</div>
<div class="callout">
<strong>Credit interpretation.</strong> JPM currently shows a larger CET1 ratio and lower reported net charge-off rate in the selected firmwide metrics, while the nonaccrual-loan comparison is mixed. Reported RoTCE is shown as disclosed and is not normalized for JPM's significant 2Q26 Corporate gains. The purpose of this section is to determine whether a spread gap is fundamentally justified before treating it as excess relative value.
</div>
<div class="source">
Sources as of {escape(fsrc['as_of'])}: 
<a href="{escape(fsrc['citi_source_url'])}">{escape(fsrc['citi_source_name'])}</a> ·
<a href="{escape(fsrc['jpm_source_url'])}">{escape(fsrc['jpm_source_name'])}</a>
</div>

<h2>4. Market valuation</h2>
<div class="tablewrap">
<table><thead><tr><th>Issuer</th><th>Price</th><th>YTC</th><th>Matched Treasury</th><th>YTC−Treasury</th><th>Duration to call</th><th>DV01</th><th>CS01</th><th>Volume / 20-obs median</th></tr></thead>
<tbody>{risk_rows}</tbody></table>
</div>
<div class="grid2">
<div class="figure"><img src="figures/real_citi_jpm_price_history.png"><div class="caption">FINRA end-of-day reported-price history used by the bond-pricing workflow.</div></div>
<div class="figure"><img src="figures/real_citi_jpm_ytc_treasury_history.png"><div class="caption">Yield to first par call versus the Treasury yield interpolated to each bond's first par-call horizon.</div></div>
</div>
<div class="grid2">
<div class="figure"><img src="figures/real_citi_jpm_treasury_spreads.png"><div class="caption">YTC minus matched Treasury yield for CITI and JPM.</div></div>
<div class="figure"><img src="figures/real_citi_jpm_pair_spread.png"><div class="caption">CITI minus JPM spread differential against its lagged historical benchmark.</div></div>
</div>

<h2>5. Relative value</h2>
<div class="figure"><img src="figures/real_citi_jpm_zscore.png"><div class="caption">Lagged historical z-score. The current observation is excluded from its own rolling mean and standard deviation.</div></div>
<div class="callout">
<strong>Interpretation.</strong> A z-score is a screening signal, not a trade instruction. The next sections test whether the signal survives risk decomposition, implementation cost and out-of-sample validation.
</div>

<h2>6. Risk-factor decomposition</h2>
<p>
The latest yield change is decomposed as <strong>Rates + Systematic Credit + Liquidity + Idiosyncratic Credit</strong>.
The systematic credit term is estimated from the ICE BofA US Corporate Index OAS obtained through FRED, using only trailing observations for the regression coefficients.
</p>
<div class="source">Systematic-credit source: <a href="https://fred.stlouisfed.org/series/BAMLC0A0CM">ICE BofA US Corporate Index Option-Adjusted Spread (FRED)</a>.</div>
<div class="tablewrap">
<table><thead><tr><th>Issuer</th><th>ΔYTC</th><th>Rates</th><th>Systematic credit</th><th>Liquidity</th><th>Idiosyncratic credit</th><th>ΔSpread</th></tr></thead>
<tbody>{factor_rows}</tbody></table>
</div>
<div class="grid2">
<div class="figure"><img src="figures/real_citi_jpm_cob_bp_decomposition.png"><div class="caption">COB basis-point factor decomposition.</div></div>
<div class="figure"><img src="figures/real_citi_jpm_dv01_cs01.png"><div class="caption">Current DV01 and CS01 per $10mm face.</div></div>
</div>
<div class="grid2">
<div class="figure"><img src="figures/real_citi_jpm_krd.png"><div class="caption">Approximate key-rate DV01 by Treasury node.</div></div>
<div class="figure"><img src="figures/real_citi_jpm_credit_factor_history.png"><div class="caption">Recent broad-IG systematic-credit factor and issuer-specific residual spread changes.</div></div>
</div>

<h3>Issuer-level first-order P&amp;L explain</h3>
<div class="tablewrap">
<table><thead><tr><th>Issuer</th><th>Rates</th><th>Systematic credit</th><th>Liquidity</th><th>Idiosyncratic</th><th>Factor total</th><th>Observed clean-price P&amp;L</th><th>Residual</th></tr></thead>
<tbody>{pnl_rows}</tbody></table>
</div>

<h2>7. Historical validation</h2>
<div class="tablewrap">
<table><thead><tr><th>Horizon</th><th>Signal observations</th><th>Avg signed convergence</th><th>Hit rate</th><th>Avg gross return estimate</th></tr></thead>
<tbody>{signal_rows}</tbody></table>
</div>
<h3 style="margin-top:18px">Independent-event backtest</h3>
<div class="tablewrap">
<table><thead><tr><th>Horizon</th><th>Events</th><th>Gross hit rate</th><th>Avg gross return</th><th>Avg net return</th><th>Net-positive rate</th></tr></thead>
<tbody>{event_rows}</tbody></table>
</div>

<h2>8. Execution &amp; liquidity</h2>
<div class="kpis">
<div class="kpi"><div class="k">CITI current reported volume</div><div class="v">{money_mm(citi.displayed_volume)}</div><div class="note">{fmt(citi.volume_vs_20obs_median,2,'x')} recent median</div></div>
<div class="kpi"><div class="k">JPM current reported volume</div><div class="v">{money_mm(jpm.displayed_volume)}</div><div class="note">{fmt(jpm.volume_vs_20obs_median,2,'x')} recent median</div></div>
<div class="kpi"><div class="k">20-obs gross return estimate</div><div class="v">{fmt(gross20,2,' bp')}</div><div class="note">Avg signed convergence {fmt(conv20,2,' bp')} · hit rate {pct(hit20)}</div></div>
<div class="kpi"><div class="k">Execution gate</div><div class="v">{execution_gate}</div><div class="note">{fmt(cost,1,' bp')} pair cost assumption → net {fmt(net20,2,' bp')}</div></div>
</div>
<div class="figure"><img src="figures/real_citi_jpm_liquidity_proxy.png"><div class="caption">FINRA reported-volume field relative to its 20-observation median. Capped values are treated as disclosed lower bounds. This is a liquidity diagnostic, not executable dealer depth or an RFQ quote.</div></div>
<div class="callout">
<strong>Execution discipline.</strong> A signal should survive transaction cost and liquidity constraints before becoming an order. With the current historical gross-return estimate and the configured round-trip cost assumption, the execution gate is <strong>{execution_gate}</strong>.
</div>

<h2>9. Portfolio impact</h2>
<p>
The section below sizes a <strong>{money_mm(pair.citi_face_usd)} CITI base leg</strong> and computes the JPM face required to make the reference pair approximately DV01-neutral.
The reference sleeve of {money_mm(reference_sleeve)} is used only to put the trade size in portfolio context.
</p>
<div class="kpis">
<div class="kpi"><div class="k">Signal direction</div><div class="v" style="font-size:18px">{escape(str(pair.direction))}</div><div class="note">What-if risk sizing; PM decision remains {decision}</div></div>
<div class="kpi"><div class="k">JPM DV01-hedge face</div><div class="v">{money_mm(pair.jpm_face_usd_dv01_hedged)}</div><div class="note">{fmt(pair.jpm_per_citi_face_ratio,3,'x')} per CITI face</div></div>
<div class="kpi"><div class="k">Net DV01</div><div class="v">{money(pair.net_dv01_usd_per_bp)}</div><div class="note">USD per 1 bp</div></div>
<div class="kpi"><div class="k">Net CS01</div><div class="v">{money(pair.net_cs01_usd_per_bp)}</div><div class="note">USD per 1 bp</div></div>
<div class="kpi"><div class="k">Gross market value / sleeve</div><div class="v">{pct(gross_mv_pct)}</div><div class="note">Sizing context</div></div>
<div class="kpi"><div class="k">Net market value / sleeve</div><div class="v">{pct(net_mv_pct)}</div><div class="note">Direction-sensitive</div></div>
<div class="kpi"><div class="k">Gross DV01</div><div class="v">{money(pair.gross_dv01_usd_per_bp)}</div><div class="note">USD per bp</div></div>
<div class="kpi"><div class="k">Gross CS01</div><div class="v">{money(pair.gross_cs01_usd_per_bp)}</div><div class="note">USD per bp</div></div>
</div>
<div class="grid2">
<div class="figure"><img src="figures/real_citi_jpm_pair_factor_pnl.png"><div class="caption">COB P&amp;L explain for the reference DV01-neutral pair in the raw signal direction.</div></div>
<div class="figure"><img src="figures/real_citi_jpm_pair_stress.png"><div class="caption">Reference-pair stress P&amp;L under rate, common-credit, issuer-specific and liquidity shocks.</div></div>
</div>
<div class="tablewrap" style="margin-top:14px">
<table><thead><tr><th>Scenario</th><th>Rates</th><th>Common credit</th><th>CITI idio</th><th>JPM idio</th><th>CITI liquidity</th><th>JPM liquidity</th><th>Pair P&amp;L</th></tr></thead>
<tbody>{stress_rows}</tbody></table>
</div>

<h2>10. PM decision</h2>
<div class="panel decision">
<div class="decisionline">{decision}</div>
<p>
The dashboard separates a market signal from an investable decision. The current mean-reversion direction is
<strong>{direction}</strong>, but the validation and execution gates do not support implementation.
The risk and portfolio sections therefore show the exposure that would be created if the trade were considered, rather than presenting it as an executed position.
</p>
</div>

<h2>Methodology &amp; controls</h2>
<div class="grid2">
<div class="panel soft"><h3>Spread measure</h3><div class="eq">YTC−Treasury = Yield to First Par Call − Interpolated Treasury Yield</div><p class="small">The measure is not labeled OAS because the embedded call option is not separately valued.</p></div>
<div class="panel soft"><h3>Risk sensitivities</h3><div class="eq">DV01 ≈ Market Value × Modified Duration × 0.0001
CS01 ≈ Market Value × Spread Duration × 0.0001</div><p class="small">Spread duration is proxied by modified duration to first par call.</p></div>
</div>
<div class="grid2" style="margin-top:16px">
<div class="panel soft"><h3>COB factor identity</h3><div class="eq">ΔYTC = Rates + Systematic Credit Proxy + Liquidity + Idiosyncratic Credit</div><p class="small">The systematic term uses the ICE BofA US Corporate Index OAS via FRED. Liquidity is a lagged regression contribution using the available FINRA reported-volume field.</p></div>
<div class="panel soft"><h3>First-order P&amp;L</h3><div class="eq">Rate P&amp;L ≈ −DV01 × ΔRates(bp)
Credit P&amp;L ≈ −CS01 × ΔCreditSpread(bp)</div><p class="small">A pricing residual is retained rather than forcing the approximation to equal observed clean-price P&amp;L.</p></div>
</div>

<div class="footer">
Independent research dashboard. Market-data availability, use and redistribution remain subject to the terms of the underlying data providers.
Issuer fundamentals are sourced from official company disclosures. Risk, execution and stress outputs are research estimates and do not constitute investment advice.
</div>
</main>
</body>
</html>"""

    out = DOCS / "real_citi_jpm_dashboard.html"
    out.write_text(html, encoding="utf-8")
    # Keep the GitHub Pages landing page synchronized.
    (DOCS / "index.html").write_text(html, encoding="utf-8")
    print(f"Wrote {out}")
    print(f"Wrote {DOCS / 'index.html'}")


if __name__ == "__main__":
    main()
