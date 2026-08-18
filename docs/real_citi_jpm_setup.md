# Real CITI / JPM pair setup

The real-data module compares:

- Citigroup Inc. 172967ME8
- JPMorgan Chase & Co. 46647PBE5

Raw FINRA files remain local under `data/raw/trace/` and are ignored by git.

## Market-spread construction

For each available FINRA daily observation, the pipeline:

1. uses the representative TRACE price;
2. solves yield to the first ordinary par-call date (YTC);
3. interpolates the official U.S. Treasury par curve to the same call date;
4. computes `YTC − Treasury` in basis points;
5. forms the CITI-minus-JPM spread differential;
6. computes a lagged 252-observation z-score;
7. validates the raw mean-reversion signal over 5, 20 and 60 observations.

The market spread is labeled **YTC−Treasury spread**, not OAS. The public-data implementation does not separately value the embedded issuer call option.

## Decision logic

A statistical z-score is only a raw signal. The pipeline then checks historical signal-day and non-overlapping event performance. A raw signal can therefore result in a final **No trade** PM decision when historical validation is negative or too sparse.
