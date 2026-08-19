# PM Dashboard Update

This update rebuilds the CITI/JPM dashboard around an institutional portfolio-management workflow.

Dashboard sections:
1. Executive portfolio view
2. Investment idea
3. Fundamental credit
4. Market valuation
5. Relative value
6. Risk-factor decomposition
7. Historical validation
8. Execution and liquidity
9. Portfolio impact and stress
10. PM decision

New analytics:
- 2Q26 issuer fundamental-credit comparison
- COB basis-point factor decomposition
- DV01, CS01 and approximate key-rate DV01
- systematic credit proxy, liquidity contribution and idiosyncratic residual
- issuer-level first-order P&L explain
- execution gate comparing historical return estimate with transaction-cost assumption
- DV01-neutral pair sizing
- reference-sleeve sizing context
- rate, common-credit, issuer-specific and liquidity stress scenarios
- longer white-background research dashboard

Run:

```bash
python scripts/build_real_citi_jpm_pair.py
python scripts/build_real_citi_jpm_risk.py
python scripts/build_real_citi_jpm_dashboard.py
```

Or:

```bash
python scripts/build_real_citi_jpm_all.py
```

The dashboard builder writes both:
- `docs/real_citi_jpm_dashboard.html`
- `docs/index.html`

Raw FINRA CSV files remain local. The update does not add raw market-data files to the repository.
