# Institutional Corporate Bond Portfolio Management

An end-to-end Python research framework for U.S. investment-grade corporate bonds.

The project is organized around the portfolio-management process:

**Market Data → Bond Pricing → Fundamental Credit → Relative Value → Risk → Validation → Liquidity & Execution → Portfolio Impact → Stress Testing → PM Decision**

The flagship case compares two senior fixed-to-floating bank bonds:

- **Citigroup Inc. — CUSIP 172967ME8**
- **JPMorgan Chase & Co. — CUSIP 46647PBE5**

The purpose is not simply to identify a statistical spread dislocation. The framework asks whether the expected compensation is sufficient after considering fundamentals, market risk, liquidity, implementation cost, and downside exposure.

---

## Project Overview

The research workflow combines four main components:

### Market and Bond Analytics

- FINRA corporate bond end-of-day observations
- U.S. Treasury curve data
- T+1 settlement handling
- accrued interest
- yield to first par call
- Treasury-matched spread
- relative-value spread differential

### Credit and Relative Value

- issuer fundamental comparison
- capital, earnings, funding, and asset-quality metrics
- CITI vs JPM spread relationship
- lagged 252-observation z-score
- 5 / 20 / 60 observation validation
- independent-event backtesting

### Risk and Portfolio Analytics

- DV01
- CS01
- key-rate duration
- systematic credit factor
- liquidity contribution
- idiosyncratic credit residual
- first-order P&L attribution
- DV01-neutral pair sizing
- stress testing
- portfolio-impact analysis

### Investment Decision

The final decision is based on the combined evidence from:

```text
Relative Value
      +
Fundamentals
      +
Risk
      +
Historical Validation
      +
Liquidity / Execution
      +
Portfolio Impact
      +
Stress
      ↓
PM Decision
```

A statistically unusual spread can therefore still result in **No Trade**.

---

# Research Case

| Field | Citigroup | JPMorgan Chase |
|---|---|---|
| CUSIP | `172967ME8` | `46647PBE5` |
| Structure | Senior fixed-to-floating callable note | Senior fixed-to-floating callable note |
| Fixed coupon | 3.980% | 2.739% |
| First par call | 2029-03-20 | 2029-10-15 |
| Maturity | 2030-03-20 | 2030-10-15 |
| Issue size | $2.50bn | $3.75bn |

The securities are comparable large-bank credit exposures, but they are not identical instruments. The analysis therefore treats their spread relationship as a relative-value framework rather than an arbitrage relationship.

---

# Data

## FINRA Corporate Bond Observations

Local FINRA Corporate & Agency Bond Trade Activity files are used for the bond-market observations.

Expected files:

```text
data/raw/trace/CITI_172967ME8.csv
data/raw/trace/JPM_46647PBE5.csv
```

The workflow normalizes:

- date
- reported price
- reported volume
- capped-volume status

For this end-of-day workflow, the bond price is treated as the latest reported sale price.

A displayed value such as:

```text
5MM+
```

is preserved as a disclosed lower bound rather than treated as an exact $5 million amount.

Raw FINRA files remain local and are excluded from version control.

## U.S. Treasury Curve

The official U.S. Treasury daily par-yield curve is used as the interest-rate benchmark.

The Treasury yield is interpolated to each bond's remaining first-par-call horizon.

## Systematic Credit Factor

The ICE BofA U.S. Corporate Index Option-Adjusted Spread from FRED is used as the broad investment-grade credit factor.

Series:

```text
BAMLC0A0CM
```

## Fundamental Credit Data

The project includes a versioned 2Q26 issuer-fundamental snapshot covering:

- CET1 ratio
- RoTCE
- net income
- net interest income
- total assets
- loans
- deposits
- net charge-off rate
- nonaccrual loans
- allowance coverage

The inputs are stored under:

```text
config/citi_jpm_fundamentals_2q26.csv
config/citi_jpm_fundamental_sources.json
```

---

# Bond Pricing

The bonds are analyzed using yield to first par call.

For each observation:

```text
Trade Date
    ↓
T+1 Settlement
    ↓
Accrued Interest
    ↓
Remaining Fixed Cash Flows
    ↓
Yield to First Par Call
```

The core pricing functions are implemented in:

```text
src/corporate_bond_pm/bond_math.py
```

The market spread measure is:

```text
YTC − Treasury
=
Yield to First Par Call
−
Interpolated Treasury Yield
```

This measure is not labeled OAS because the embedded call option is not separately valued.

---

# Relative Value

For the two bonds:

```text
Pair Spread_t
=
CITI Spread_t
−
JPM Spread_t
```

The historical signal is a lagged rolling z-score:

```text
Z_t
=
(Pair Spread_t − Lagged Mean)
/
Lagged Standard Deviation
```

The rolling benchmark uses the prior 252 aligned observations, excluding the current observation.

The z-score is a screening signal rather than an automatic trade rule.

---

# Fundamental Credit

Relative value is considered together with issuer credit quality.

The framework evaluates whether the observed spread difference is consistent with differences in:

- capital strength
- earnings power
- funding
- loan quality
- credit losses
- balance-sheet scale

The objective is to distinguish:

```text
Fundamentally justified spread difference
```

from:

```text
Potential excess relative-value difference
```

---

# Risk-Factor Decomposition

The close-of-business yield move is decomposed into rates and credit:

```text
ΔYTC
=
ΔTreasury
+
ΔCredit Spread
```

Credit-spread movement is further decomposed as:

```text
ΔCredit Spread
=
Systematic Credit
+
Liquidity
+
Idiosyncratic Credit
```

A trailing regression uses:

```text
ΔSpread_i,t
=
α_i
+
β_IG,i × ΔIG_OAS_t
+
β_LIQ,i × LiquidityShock_i,t
+
ε_i,t
```

where:

- `ΔIG_OAS` is the broad investment-grade corporate credit factor
- `LiquidityShock` is derived from the available reported-volume field
- `ε` is the residual issuer-specific component

The regression uses only observations available before the current date.

---

# DV01, CS01 and Key-Rate Risk

Dollar interest-rate sensitivity:

```text
DV01
≈
Market Value × Modified Duration × 0.0001
```

Dollar spread sensitivity:

```text
CS01
≈
Market Value × Spread Duration × 0.0001
```

The framework also reports approximate key-rate DV01 across standard Treasury nodes.

Within this implementation, duration to first par call is used as a transparent spread-duration proxy.

First-order P&L attribution:

```text
Rate P&L
≈
−DV01 × ΔRates(bp)

Credit P&L
≈
−CS01 × ΔCreditSpread(bp)
```

A residual is retained rather than forcing the attribution to equal the full observed price move.

---

# Historical Validation

Signals are evaluated chronologically over:

```text
5 observations
20 observations
60 observations
```

The project reports both:

- signal-day diagnostics
- independent-event backtests

Independent events are created when the selected threshold is crossed, while overlapping holding periods are blocked.

This reduces the risk of counting the same multi-day signal episode as multiple independent trades.

The validation process is intended to answer:

> Does the observed relative-value relationship actually have a history of convergence?

---

# Liquidity and Execution

The execution layer considers:

- reported volume
- volume relative to recent history
- capped-volume status
- recent spread volatility
- transaction-cost assumption
- expected convergence after implementation cost

The execution gate compares:

```text
Expected Gross Convergence
−
Estimated Implementation Cost
=
Expected Net Value
```

Reported volume is used only as a liquidity diagnostic. It is not treated as executable dealer depth.

---

# Portfolio Impact

A reference relative-value position is translated into portfolio risk.

The current framework begins with a CITI reference leg and calculates the JPM notional required to approximately neutralize DV01:

```text
JPM Face
=
CITI Face
×
DV01_CITI
/
DV01_JPM
```

The resulting analysis includes:

- gross market value
- net market value
- gross DV01
- net DV01
- gross CS01
- net CS01
- portfolio-sizing context

The portfolio sleeve used in the dashboard is a configurable reference scale and is not presented as an actual portfolio holding.

---

# Stress Testing

The reference pair is evaluated under:

- rates shocks
- broad credit widening
- CITI-specific widening
- JPM-specific widening
- liquidity deterioration
- combined risk-off conditions

The first-order stress framework is:

```text
Stress P&L
≈
−DV01 × Rate Shock
−
CS01 × Credit / Liquidity Shock
```

The stress framework is designed to show how the proposed trade behaves when the investment thesis is wrong or market conditions deteriorate.

---

# Dashboard

The repository includes a static research dashboard summarizing the main outputs of the CITI/JPM analysis.

It provides a consolidated view of:

- market valuation
- fundamental credit
- relative value
- risk-factor decomposition
- DV01 / CS01 / KRD
- validation
- liquidity and execution
- portfolio impact
- stress
- final PM decision

GitHub Pages:

```text
https://kevinli25423-cmd.github.io/corporate-bond-portfolio-management/
```

Generated files:

```text
docs/index.html
docs/real_citi_jpm_dashboard.html
```

---

# Repository Structure

```text
.
├── README.md
├── app_real.py
├── requirements.txt
├── requirements-dashboard.txt
│
├── config/
│   ├── real_citi_jpm_pair.json
│   ├── citi_jpm_dashboard_scenario.json
│   ├── citi_jpm_fundamentals_2q26.csv
│   └── citi_jpm_fundamental_sources.json
│
├── data/
│   ├── raw/
│   │   └── trace/
│   └── processed/
│       └── real/
│
├── docs/
│   ├── index.html
│   ├── real_citi_jpm_dashboard.html
│   ├── figures/
│   └── results/
│       └── real/
│
├── scripts/
│   ├── build_real_citi_jpm_pair.py
│   ├── build_real_citi_jpm_risk.py
│   ├── build_real_citi_jpm_dashboard.py
│   └── check_finra_api_access.py
│
├── src/
│   └── corporate_bond_pm/
│       ├── bond_math.py
│       ├── trace_real.py
│       ├── treasury_real.py
│       ├── market_factor.py
│       ├── real_pair.py
│       ├── real_risk_decomposition.py
│       ├── risk.py
│       ├── relative_value.py
│       ├── fundamentals.py
│       ├── expected_return.py
│       ├── optimizer.py
│       ├── stress.py
│       ├── trading.py
│       ├── attribution.py
│       └── validation.py
│
└── tests/
```

---

# Quick Start

Clone the repository:

```bash
git clone https://github.com/kevinli25423-cmd/corporate-bond-portfolio-management.git
cd corporate-bond-portfolio-management
```

Create an environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Place the local FINRA files under:

```text
data/raw/trace/
```

Run the market and relative-value analysis:

```bash
python scripts/build_real_citi_jpm_pair.py
```

Run the risk and portfolio analysis:

```bash
python scripts/build_real_citi_jpm_risk.py
```

Build the dashboard:

```bash
python scripts/build_real_citi_jpm_dashboard.py
```

Open locally:

```bash
open docs/index.html
```

Run tests:

```bash
python -m pytest tests -v
```

---

# Main Outputs

Local processed market data:

```text
data/processed/real/
```

Derived research outputs:

```text
docs/results/real/
```

Charts:

```text
docs/figures/
```

Dashboard:

```text
docs/index.html
```

---

# Design Principles

The project follows several controls:

- lagged signal formation
- chronological validation
- independent-event testing
- T+1 settlement treatment
- preservation of capped-volume information
- broad external systematic-credit factor
- explicit liquidity assumptions
- explicit transaction costs
- residual retention in P&L attribution
- separation of signal generation from PM decision

The framework is intentionally designed so that an apparently attractive relative-value signal can still be rejected.

---

# Limitations

This project uses public and locally stored market information, so several limitations remain important.

- `YTC − Treasury` is not OAS.
- FINRA reported prices are not executable institutional mid-prices.
- reported volume is not dealer depth.
- CS01 uses a duration-based spread-risk approximation.
- first-order risk attribution does not capture all convexity or optionality effects.
- the broad IG credit factor does not isolate financial-sector risk.
- stress scenarios are decision-support assumptions rather than forecasts.

These limitations are retained explicitly rather than hidden inside the model.

---

# Data Governance

Raw FINRA observations and locally processed market-data files are excluded from the public repository.

The public repository contains:

- source code
- configuration
- methodology
- issuer disclosure references
- derived research outputs
- charts
- dashboard files
- tests

Use and redistribution of third-party data remain subject to the terms of the underlying data providers.

---

# Research Philosophy

The project is built around a simple principle:

> **A wide spread is not automatically a buy.**

A corporate-bond trade should be considered only after asking:

```text
What does the bond offer over Treasuries?
        ↓
Why does it differ from a comparable bond?
        ↓
Is the difference supported by fundamentals?
        ↓
What risk factors are driving the move?
        ↓
Has the relationship historically converged?
        ↓
Will the expected return survive implementation cost?
        ↓
What does the position add to portfolio risk?
        ↓
What happens under stress?
        ↓
Is the trade worth taking?
```

---

# Disclaimer

This repository is an independent research and educational project and does not constitute investment advice, a recommendation, or an offer to transact in any security.

Market observations may be delayed, incomplete, capped, or subject to provider-specific reporting conventions. Derived spreads, sensitivities, factor decompositions, execution estimates and stress results are research calculations and should not be interpreted as executable market quotations or actual portfolio positions.

---

## License

MIT License. See [`LICENSE`](LICENSE).
