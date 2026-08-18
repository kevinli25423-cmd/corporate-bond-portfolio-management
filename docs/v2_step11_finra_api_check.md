# V2 Step 1.1 — FINRA API Access Check

This checkpoint verifies two things without storing credentials in the repository:

1. The Public FINRA API credential can authenticate through FINRA Identity Platform (FIP).
2. Whether the single-bond Corporate & Agency Trade Activity dataset used by the public website is also exposed through the documented FINRA Query API.

Run:

```bash
python scripts/check_finra_api_access.py
```

If environment variables are not already set, the script prompts locally for the Client ID and Client Secret; the secret input is hidden. It never prints the access token or Client Secret.

The script first checks the documented `fixedIncomeMarket/treasuryDailyAggregates` metadata endpoint as a control. It then tests metadata availability for the single-bond Corporate & Agency Trade Activity dataset. No web-page scraping is performed.
