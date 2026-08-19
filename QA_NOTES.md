# Dashboard QA corrections

This QA pass corrects and tightens the public CITI/JPM dashboard implementation.

Corrections included:
- JPMorgan 2Q26 reported RoTCE corrected to 29.0% from the earlier 23.0% entry.
- Bond YTC and duration now use a standard T+1 business-day settlement-date approximation.
- FINRA Trade Activity end-of-day rows are handled as last-sale observations rather than transaction-level medians.
- Capped FINRA volume values such as `5MM+` retain a cap flag and are treated as disclosed lower bounds.
- Treasury interpolation accepts numeric tenor columns after CSV reload.
- Systematic credit is now based on the ICE BofA US Corporate Index OAS from FRED rather than a mechanically constructed two-bond common factor.
- Liquidity stresses can differ by issuer rather than forcing the same shock on both legs.
- Dashboard wording distinguishes reported volume, execution diagnostics, first-order risk estimates, and disclosed company fundamentals.

Validation:
- Full reconstructed test suite: 23 passed.
- Static Python compilation: passed.
