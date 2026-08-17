# Data Contract

The analytical pipeline expects six input tables under `data/demo/`.

## `security_master.csv`

Static or event-driven bond terms:

- `security_id`
- `issuer`
- `issuer_name`
- `cusip`
- `coupon_pct`
- `maturity`
- `issue_date`
- `seniority`
- `callable`
- `issue_size_mm`
- `rating`
- `representative`

## `market_daily.csv`

Daily bond analytics:

- `date`
- `security_id`
- `issuer`
- `price`
- `yield_pct`
- `oas_bp`
- `modified_duration`
- `spread_duration`
- `treasury_yield_pct`
- `carry_1m_bp`
- `rolldown_1m_bp`

## `cds_daily.csv`

Daily issuer credit anchor:

- `date`
- `issuer`
- `cds_5y_bp`

## `fundamentals.csv`

Point-in-time issuer fundamentals keyed by `effective_date`.

## `liquidity_daily.csv`

Daily or rolling liquidity measures:

- liquidity score
- trade count
- active days
- price dispersion

## `holdings.csv`

Portfolio weights for the representative-bond sleeve and cash.

All included data are synthetic. The separation of tables is deliberate: it keeps security terms, market observations, credit fundamentals, liquidity, and portfolio state independently auditable.
