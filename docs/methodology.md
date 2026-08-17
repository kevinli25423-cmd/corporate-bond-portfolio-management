# Methodology Notes

## 1. Credit analysis

The fundamental scorecard compares capital, asset quality, funding/liquidity, and earnings. The score is used for structured comparison and thesis validation; it is not mechanically converted into a fair-spread number.

## 2. Historical relative value

For two comparable bonds:

```text
D_t = OAS_A,t - OAS_B,t
```

The rolling mean and standard deviation use `shift(1)` so the current observation does not enter its own historical benchmark.

## 3. Fair spread differential

```text
D_fair = D_credit + D_duration + D_liquidity + D_structure
RV = D_market - D_fair
```

The residual is interpreted as unexplained spread or potential relative value rather than certain mispricing.

## 4. Regression confirmation

A pooled rolling-window regression estimates log OAS from issuer CDS, spread duration, liquidity, issue age, and issue size. It is intentionally used as one confirmation signal rather than the sole valuation engine.

## 5. Expected return

```text
E[ΔSpread] = -q × RV
E[R] = Carry + RollDown - SpreadDuration × E[ΔSpread] - TransactionCost
```

`q` is a modeling assumption in the demo and should be calibrated out-of-sample in a production research process.

## 6. Risk

The project measures DV01, CS01, and simple key-rate-duration allocations. These risk measures feed position sizing and portfolio constraints.

## 7. Optimization

The optimizer balances expected return, covariance risk, and turnover under concentration, cash, and duration constraints. A separate overlay can moderate concentration or raise cash under a more defensive scenario.

## 8. Stress and attribution

Stress testing compares current, optimized, and final portfolios under common scenarios. Attribution then separates rates, common spread, issuer/RV, carry, and roll-down contributions so the original thesis can be evaluated.
