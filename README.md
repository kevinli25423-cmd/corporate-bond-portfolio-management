# Institutional Corporate Bond Portfolio Management

An independent personal research project exploring institutional U.S. investment-grade corporate bond portfolio management with Python.

The framework connects:

**Credit Analysis → Relative Value → Risk Decomposition → Expected Return → Portfolio Optimization → Stress Testing → Portfolio Construction → Trading → P&L Attribution**

The central research question is:

> When does additional corporate-bond spread provide enough compensation for credit, liquidity, concentration, and tail risk?

## Scope

The repository simulates a **$100 million Financials sleeve** within a broader investment-grade corporate bond framework. The initial research universe uses representative bonds from:

- JPMorgan Chase
- Bank of America
- Citigroup
- Wells Fargo

Named issuers are used solely as public-market examples. All bond-level spreads, CDS levels, holdings, liquidity observations, expected returns, and scenario results in `data/demo/` are synthetic and illustrative.

## What the project implements

- Security master and point-in-time data architecture
- Fundamental credit scorecard
- Historical pair relative value with lagged rolling z-scores
- CDS and bond-characteristic fair-spread decomposition
- Cross-sectional regression as a confirmation signal
- DV01, CS01, and key-rate-duration analysis
- Issuer concentration and liquidity analytics
- Carry + roll-down + spread-convergence expected return
- Transaction-cost adjustment
- Constrained portfolio optimization
- Normal, slowdown, and crisis stress scenarios
- Portfolio construction overlay after optimization
- Trade sizing and trade blotter
- One-month P&L attribution and thesis validation
- Optional Streamlit dashboard

## Analytical philosophy

A wide spread is not automatically a buy signal. The workflow asks whether the spread difference is explainable and whether the remaining compensation is attractive after risk and trading costs.

```text
Observed Market Spread
        ↓
Historical Relationship
        ↓
Market-Implied Credit
        ↓
Fundamental Credit
        ↓
Bond / Liquidity Characteristics
        ↓
Relative-Value Residual
        ↓
Expected Convergence
        ↓
Expected Return
        ↓
Risk Budget
        ↓
Portfolio Allocation
        ↓
Stress Testing
        ↓
Attribution
```

Portfolio optimization is treated as a decision-support layer, not as an automatic final allocation rule.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_demo_data.py
python scripts/run_pipeline.py
```

Optional dashboard:

```bash
# Optional dashboard dependencies
pip install -r requirements-dashboard.txt

# Launch the dashboard
streamlit run app.py
```

Run tests:

```bash
python -m pytest tests -v
```

## Repository structure

```text
.
├── app.py
├── config/
│   └── project_config.json
├── data/
│   ├── demo/
│   └── output/
├── docs/
│   ├── data_contract.md
│   └── methodology.md
├── notebooks/
│   └── 01_end_to_end_research.ipynb
├── scripts/
│   ├── generate_demo_data.py
│   └── run_pipeline.py
├── src/
│   └── corporate_bond_pm/
│       ├── attribution.py
│       ├── data.py
│       ├── expected_return.py
│       ├── fundamentals.py
│       ├── optimizer.py
│       ├── relative_value.py
│       ├── risk.py
│       ├── stress.py
│       └── trading.py
└── tests/
```

## Core formulas

Historical pair spread:

```text
D_t = OAS_A,t - OAS_B,t
Z_t = (D_t - lagged rolling mean) / lagged rolling standard deviation
```

Fair differential:

```text
D_fair = D_credit + D_duration + D_liquidity + D_structure
RV = D_market - D_fair
```

Spread-price approximation:

```text
ΔP / P ≈ -SpreadDuration × ΔSpread
```

Expected return:

```text
E[R] = Carry + RollDown - SpreadDuration × E[ΔSpread] + RatesView - TransactionCost
```

Portfolio objective:

```text
max_w  w'α - λ(w'Σw) - γTC(w)
```

subject to fully invested, issuer concentration, cash, and duration constraints.

## Data design

The included demo dataset is deterministic and synthetic so the full workflow can be reproduced without proprietary data. The same schemas can be populated with appropriately licensed market, transaction, portfolio, and credit data.

The model intentionally keeps market data, fundamentals, liquidity observations, and security terms in separate tables so that point-in-time joins and data lineage remain explicit.

## Relative-value interpretation

For two comparable bonds:

```text
D_market = OAS_A - OAS_B
D_credit = CDS_A - CDS_B
D_fair = D_credit + D_bond + D_liquidity
RV = D_market - D_fair
```

A positive `RV` means Bond A trades wider than the spread difference explained by the selected factors. It indicates potential relative cheapness, not a guaranteed mispricing.

The project combines three signals:

1. Historical relative spread
2. CDS / bond-characteristic fair differential
3. Cross-sectional regression residual

## Risk framework

Approximate dollar sensitivities:

```text
DV01 ≈ ModifiedDuration × MarketValue × 0.0001
CS01 ≈ SpreadDuration × MarketValue × 0.0001
```

Rates exposure is also decomposed across 2Y, 3Y, 5Y, 7Y, and 10Y key-rate nodes.

## Stress testing

The project includes three illustrative regimes:

- Normal
- Slowdown
- Crisis

Each scenario combines Treasury shocks, Financials spread shocks, issuer sensitivity multipliers, and liquidity costs. The purpose is to compare expected compensation with downside exposure rather than to forecast the exact timing of market stress.

## P&L attribution

The attribution layer separates:

```text
Total P&L
= Rates
+ Market Spread
+ Issuer / Relative Value
+ Carry
+ Roll-Down
```

This helps distinguish whether a position worked because the relative-value thesis converged or because broad market factors moved favorably.

## Disclaimer

This repository is an independent personal research and educational project. Synthetic examples are not live market quotations, investment advice, proprietary data, or actual portfolio holdings.
