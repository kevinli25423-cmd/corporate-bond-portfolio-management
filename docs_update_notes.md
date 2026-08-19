# Risk Dashboard Update

Adds:
- longer white-background dashboard
- COB basis-point factor decomposition
- DV01 and CS01 per $10mm face
- systematic credit proxy
- liquidity contribution
- idiosyncratic credit residual
- key-rate DV01
- first-order issuer P&L explain
- hypothetical DV01-neutral pair risk
- additional price, yield, factor and liquidity charts

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

The dashboard builder writes both `docs/real_citi_jpm_dashboard.html` and `docs/index.html`.
