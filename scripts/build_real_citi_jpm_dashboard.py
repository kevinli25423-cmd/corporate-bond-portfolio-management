from __future__ import annotations

from html import escape
from pathlib import Path
import math

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "docs" / "results" / "real"
DOCS = ROOT / "docs"


def fmt(v, digits=2, suffix=""):
    try:
        if v is None or math.isnan(float(v)):
            return "—"
        return f"{float(v):,.{digits}f}{suffix}"
    except Exception:
        return escape(str(v))


def pct(v):
    try:
        if math.isnan(float(v)):
            return "—"
        return f"{100*float(v):.1f}%"
    except Exception:
        return "—"


def build() -> str:
    latest_path = RESULT / "citi_jpm_latest.csv"
    signal_path = RESULT / "citi_jpm_signal_summary.csv"
    event_path = RESULT / "citi_jpm_event_summary.csv"
    if not latest_path.exists():
        raise FileNotFoundError("Run `python scripts/build_real_citi_jpm_pair.py` first.")

    latest = pd.read_csv(latest_path).iloc[0]
    signal = pd.read_csv(signal_path)
    events = pd.read_csv(event_path)

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

    raw_signal = escape(str(latest.raw_signal))
    direction = escape(str(latest.mean_reversion_direction))
    validation = escape(str(latest.validation_status))
    decision = escape(str(latest.pm_decision))
    reason = escape(str(latest.validation_reason))

    return f'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Real CITI / JPM Relative-Value Dashboard</title>
<style>
:root{{--bg:#07111f;--panel:#0d1b2a;--line:#20364b;--text:#eef5fb;--muted:#91a8bc;--a:#50b8ff;--g:#43d6ad;}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(180deg,#06101c,#081522);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}}
main{{width:min(1160px,calc(100% - 28px));margin:auto;padding:54px 0 70px}}h1{{font-size:48px;line-height:1.05;margin:8px 0 12px}}h2{{margin-top:38px}}p,.muted{{color:var(--muted);line-height:1.55}}.eyebrow{{color:var(--a);font-weight:800;letter-spacing:.13em;text-transform:uppercase;font-size:12px}}
.kpis{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:24px 0}}.card{{background:rgba(13,27,42,.9);border:1px solid var(--line);border-radius:15px;padding:16px}}.k{{font-size:11px;color:var(--muted);text-transform:uppercase}}.v{{font-size:26px;font-weight:800;margin-top:8px}}.decision{{border-color:rgba(80,184,255,.5);background:linear-gradient(120deg,rgba(80,184,255,.12),rgba(67,214,173,.06))}}.decisionline{{font-size:20px;font-weight:800;margin-top:6px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}img{{width:100%;display:block;border-radius:12px;background:white}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid var(--line);font-size:13px}}th{{text-align:left;color:var(--muted);font-size:11px;text-transform:uppercase}}td:not(:first-child),th:not(:first-child){{text-align:right}}code{{color:#bde5ff}}@media(max-width:900px){{.kpis{{grid-template-columns:repeat(2,1fr)}}.grid{{grid-template-columns:1fr}}}}
</style></head><body><main>
<div class="eyebrow">Real market case study</div><h1>CITI vs JPM Relative Value</h1>
<p>Local FINRA observations + official U.S. Treasury curve. Raw FINRA files stay local; this page contains only derived analytics.</p>
<div class="kpis">
<div class="card"><div class="k">As of</div><div class="v">{escape(str(latest.as_of))}</div></div>
<div class="card"><div class="k">CITI YTC−Treasury</div><div class="v">{fmt(latest.citi_treasury_spread_bp,2,' bp')}</div></div>
<div class="card"><div class="k">JPM YTC−Treasury</div><div class="v">{fmt(latest.jpm_treasury_spread_bp,2,' bp')}</div></div>
<div class="card"><div class="k">CITI − JPM</div><div class="v">{fmt(latest.pair_spread_bp,2,' bp')}</div></div>
<div class="card"><div class="k">Lagged z-score</div><div class="v">{fmt(latest.hist_z,2,'σ')}</div></div>
<div class="card decision"><div class="k">PM decision</div><div class="v">{decision}</div><div class="muted">Validation: {validation}</div></div>
</div>
<div class="card decision"><div class="k">Signal → validation → decision</div><div class="decisionline">{raw_signal} · {direction} → {decision}</div><p class="muted">{reason}</p></div>
<div class="grid" style="margin-top:14px"><div class="card"><img src="figures/real_citi_jpm_treasury_spreads.png"><p class="muted">Yield to first par call minus Treasury par yield interpolated to each bond's first par-call date.</p></div><div class="card"><img src="figures/real_citi_jpm_pair_spread.png"><p class="muted">CITI minus JPM Treasury-spread differential with lagged historical benchmark.</p></div></div>
<div class="card" style="margin-top:14px"><img src="figures/real_citi_jpm_zscore.png"><p class="muted">Signal uses prior 252 aligned observations only. Positive z means CITI is wide relative to JPM.</p></div>
<h2>5 / 20 / 60 observation validation</h2><div class="card"><table><thead><tr><th>Horizon</th><th>Signal observations</th><th>Avg convergence</th><th>Hit rate</th><th>Avg gross return estimate</th></tr></thead><tbody>{signal_rows}</tbody></table></div>
<h2>Independent event backtest</h2><div class="card"><table><thead><tr><th>Horizon</th><th>Events</th><th>Gross hit rate</th><th>Avg gross return</th><th>Avg net return</th><th>Net-positive</th></tr></thead><tbody>{event_rows}</tbody></table></div>
<p class="muted">Spread = YTC to first par call minus interpolated Treasury yield. It is not OAS because the embedded call option is not separately valued. Backtest returns are duration-scaled research estimates, not realized executable P&amp;L.</p>
</main></body></html>'''


def main():
    html = build()
    out = DOCS / "real_citi_jpm_dashboard.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
