# V2 Step 1 — Real BAC/JPM Data Setup

The first real-data module replaces the synthetic BAC/JPM pair with actual public secondary-market transaction data and official U.S. Treasury curve data.

## Selected securities

### JPMorgan Chase & Co.
- CUSIP: `46647PEU6`
- 4.915% fixed-to-floating senior notes due January 24, 2029
- Original size: $2.0 billion
- Fixed rate through / first par-call date: January 24, 2028
- Thereafter: Compounded SOFR + 80 bp

### Bank of America Corporation
- CUSIP: `06051GMT3`
- 4.623% fixed/floating senior notes due May 9, 2029
- Original size: $2.25 billion
- Fixed rate through / first par-call date: May 9, 2028
- Thereafter: Compounded SOFR + 111 bp

These are close comparables rather than identical securities. The public proxy therefore uses **yield to first par call** and an interpolated Treasury curve, not raw yield differences and not a claim of vendor OAS.

## Step A — Export FINRA trade history manually

This project does not scrape or bypass FINRA's public interface.

1. Open FINRA Fixed Income Data / Corporate and Agency Bond Trade Activity.
2. Accept the Fixed Income Data User Agreement when prompted.
3. Search JPM CUSIP `46647PEU6`, open its trade history, export CSV, and save as `data/raw/trace/JPM_46647PEU6.csv`.
4. Search BAC CUSIP `06051GMT3`, export CSV, and save as `data/raw/trace/BAC_06051GMT3.csv`.

## Step B — Build the real pair

```bash
python scripts/build_real_bac_jpm_pair.py
```

The script downloads official Treasury daily par-yield curves for the years covered by the FINRA exports, calculates daily YTC, interpolates the Treasury curve to each first par-call date, and creates the public spread proxy.

Outputs:

```text
data/processed/real/bac_jpm_real_pair_daily.csv
data/processed/real/jpm_46647peu6_daily.csv
data/processed/real/bac_06051gmt3_daily.csv
data/processed/real/treasury_curve_daily.csv
docs/results/real/real_bac_jpm_step1.md
docs/figures/real_bac_jpm_proxy_spreads.png
docs/figures/real_bac_jpm_pair_spread.png
docs/figures/real_bac_jpm_zscore.png
```

## Spread definition

```text
TRACE representative clean price
→ yield to first par call
→ minus Treasury yield interpolated to first par call
→ public Treasury-spread proxy
```

This is intentionally **not** called OAS.

## CSV column detection

If FINRA uses unusual column labels:

```bash
python scripts/build_real_bac_jpm_pair.py \
  --date-col "YOUR DATE COLUMN" \
  --price-col "YOUR PRICE COLUMN" \
  --volume-col "YOUR QUANTITY COLUMN"
```

Raw FINRA CSVs and processed real-data CSVs are ignored by Git by default.
