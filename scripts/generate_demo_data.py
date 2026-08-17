from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RNG = np.random.default_rng(755)
OUT = ROOT / "data" / "demo"
OUT.mkdir(parents=True, exist_ok=True)


def make_security_master() -> pd.DataFrame:
    issuer_info = {
        "JPM": {"name": "JPMorgan Chase", "oas": 68.0, "cds": 52.0, "liq": 0.90},
        "BAC": {"name": "Bank of America", "oas": 80.0, "cds": 58.0, "liq": 0.82},
        "C": {"name": "Citigroup", "oas": 85.0, "cds": 63.0, "liq": 0.78},
        "WFC": {"name": "Wells Fargo", "oas": 74.0, "cds": 56.0, "liq": 0.84},
    }
    maturity_years = [2.5, 3.5, 5.0, 6.5, 8.0]
    rows = []
    anchor = pd.Timestamp("2026-08-16")
    for issuer, info in issuer_info.items():
        for i, years in enumerate(maturity_years, start=1):
            rows.append({
                "security_id": f"{issuer}_{i}",
                "issuer": issuer,
                "issuer_name": info["name"],
                "cusip": f"SYN{issuer}{i:02d}",
                "coupon_pct": round(4.00 + 0.25 * i + RNG.normal(0, 0.05), 4),
                "maturity": (anchor + pd.DateOffset(days=int(365.25 * years))).date(),
                "issue_date": (anchor - pd.DateOffset(days=int(365.25 * (0.5 + i * 0.35)))).date(),
                "seniority": "Senior Unsecured",
                "callable": False,
                "issue_size_mm": int(1500 + 350 * i + RNG.integers(-150, 150)),
                "rating": "A",
                "representative": i == 3,
                "target_oas_bp": info["oas"],
                "target_cds_bp": info["cds"],
                "base_liquidity": info["liq"],
            })
    return pd.DataFrame(rows)


def simulate_market(sm: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = pd.bdate_range(end="2026-08-14", periods=320)
    n = len(dates)

    market_factor = np.zeros(n)
    sector_factor = np.zeros(n)
    treasury = np.zeros(n)
    treasury[0] = 4.20
    for t in range(1, n):
        market_factor[t] = 0.96 * market_factor[t - 1] + RNG.normal(0, 0.65)
        sector_factor[t] = 0.93 * sector_factor[t - 1] + RNG.normal(0, 0.45)
        treasury[t] = 4.20 + 0.98 * (treasury[t - 1] - 4.20) + RNG.normal(0, 0.015)

    issuers = sorted(sm["issuer"].unique())
    issuer_noise = {issuer: np.zeros(n) for issuer in issuers}
    cds_noise = {issuer: np.zeros(n) for issuer in issuers}
    for issuer in issuers:
        for t in range(1, n):
            issuer_noise[issuer][t] = 0.92 * issuer_noise[issuer][t - 1] + RNG.normal(0, 0.55)
            cds_noise[issuer][t] = 0.94 * cds_noise[issuer][t - 1] + RNG.normal(0, 0.40)

    # Add a smooth late-period BAC widening so the research example has a visible RV signal.
    bac_widen = np.zeros(n)
    bac_widen[-25:] = np.linspace(0.0, 5.0, 25)

    market_rows, cds_rows, liq_rows = [], [], []
    for t, date in enumerate(dates):
        for issuer in issuers:
            issuer_row = sm.loc[sm["issuer"].eq(issuer)].iloc[0]
            target_cds = float(issuer_row["target_cds_bp"])
            cds = target_cds + 0.45 * market_factor[t] + 0.60 * sector_factor[t] + cds_noise[issuer][t]
            if issuer == "BAC":
                cds += 0.35 * bac_widen[t]
            cds_rows.append({"date": date, "issuer": issuer, "cds_5y_bp": max(15.0, cds)})

        for _, bond in sm.iterrows():
            issuer = bond["issuer"]
            maturity_years = max((pd.Timestamp(bond["maturity"]) - date).days / 365.25, 0.75)
            modified_duration = min(max(0.86 * maturity_years, 1.0), 7.2)
            spread_duration = modified_duration * 0.95
            curve_adj = 0.9 * (maturity_years - 5.0)
            issue_age = max((date - pd.Timestamp(bond["issue_date"])).days / 365.25, 0.0)
            age_adj = 0.45 * issue_age
            idio = RNG.normal(0, 0.45)
            oas = (
                float(bond["target_oas_bp"])
                + 0.80 * market_factor[t]
                + 0.85 * sector_factor[t]
                + issuer_noise[issuer][t]
                + curve_adj
                + age_adj
                + idio
            )
            if issuer == "BAC":
                oas += bac_widen[t]

            yld = treasury[t] + oas / 100.0
            price = 100.0 + (4.75 - yld) * modified_duration + RNG.normal(0, 0.12)
            carry_1m_bp = max(18.0, yld * 100.0 / 12.0)
            rolldown_1m_bp = max(-2.0, 4.0 - abs(maturity_years - 5.0) * 0.35)

            market_rows.append({
                "date": date,
                "security_id": bond["security_id"],
                "issuer": issuer,
                "price": price,
                "yield_pct": yld,
                "oas_bp": max(20.0, oas),
                "modified_duration": modified_duration,
                "spread_duration": spread_duration,
                "treasury_yield_pct": treasury[t],
                "carry_1m_bp": carry_1m_bp,
                "rolldown_1m_bp": rolldown_1m_bp,
            })

            base_liq = float(bond["base_liquidity"])
            liquidity_score = np.clip(
                base_liq - 0.018 * issue_age + RNG.normal(0, 0.018),
                0.35,
                0.98,
            )
            trade_count_20d = max(5, int(55 * liquidity_score + RNG.normal(0, 4)))
            active_days_20d = int(np.clip(round(20 * liquidity_score + RNG.normal(0, 1.2)), 5, 20))
            price_dispersion_bp = max(0.5, 11.0 * (1.0 - liquidity_score) + RNG.normal(0, 0.6))
            liq_rows.append({
                "date": date,
                "security_id": bond["security_id"],
                "issuer": issuer,
                "liquidity_score": liquidity_score,
                "trade_count_20d": trade_count_20d,
                "active_days_20d": active_days_20d,
                "price_dispersion_bp": price_dispersion_bp,
            })

    return pd.DataFrame(market_rows), pd.DataFrame(cds_rows), pd.DataFrame(liq_rows)


def make_fundamentals() -> pd.DataFrame:
    base = {
        "JPM": [15.3, 12.1, 4.1, 0.54, 0.48, 4.0, 118, 20.0, 5.0],
        "BAC": [14.0, 11.5, 3.2, 0.62, 0.56, 2.5, 115, 16.5, 3.0],
        "C":   [13.6, 11.4, 2.7, 0.71, 0.64, 1.0, 112, 10.5, 1.0],
        "WFC": [13.9, 11.2, 3.0, 0.65, 0.58, 2.0, 116, 14.0, 2.0],
    }
    dates = [pd.Timestamp("2025-11-05"), pd.Timestamp("2026-02-05"), pd.Timestamp("2026-05-05"), pd.Timestamp("2026-08-05")]
    rows = []
    for q, effective_date in enumerate(dates):
        for issuer, vals in base.items():
            cet1, req, tlac, nco, npl, dep, lcr, rotce, ppnr = vals
            rows.append({
                "effective_date": effective_date,
                "issuer": issuer,
                "cet1_ratio_pct": cet1 + RNG.normal(0, 0.10) + 0.03 * q,
                "required_cet1_pct": req,
                "tlac_buffer_pct": tlac + RNG.normal(0, 0.10),
                "nco_pct": max(0.05, nco + RNG.normal(0, 0.03)),
                "npl_pct": max(0.05, npl + RNG.normal(0, 0.03)),
                "deposit_growth_pct": dep + RNG.normal(0, 0.35),
                "lcr_pct": lcr + RNG.normal(0, 1.2),
                "rotce_pct": rotce + RNG.normal(0, 0.45),
                "ppnr_growth_pct": ppnr + RNG.normal(0, 0.50),
            })
    return pd.DataFrame(rows)


def make_holdings(sm: pd.DataFrame) -> pd.DataFrame:
    reps = sm.loc[sm["representative"]].set_index("issuer")["security_id"].to_dict()
    return pd.DataFrame({
        "asset": ["JPM", "BAC", "C", "WFC", "Cash"],
        "security_id": [reps["JPM"], reps["BAC"], reps["C"], reps["WFC"], "CASH"],
        "issuer": ["JPM", "BAC", "C", "WFC", "Cash"],
        "weight": [0.30, 0.15, 0.20, 0.20, 0.15],
    })


def main() -> None:
    sm = make_security_master()
    market, cds, liquidity = simulate_market(sm)
    fundamentals = make_fundamentals()
    holdings = make_holdings(sm)

    sm.drop(columns=["target_oas_bp", "target_cds_bp", "base_liquidity"]).to_csv(OUT / "security_master.csv", index=False)
    market.to_csv(OUT / "market_daily.csv", index=False)
    cds.to_csv(OUT / "cds_daily.csv", index=False)
    liquidity.to_csv(OUT / "liquidity_daily.csv", index=False)
    fundamentals.to_csv(OUT / "fundamentals.csv", index=False)
    holdings.to_csv(OUT / "holdings.csv", index=False)
    print(f"Synthetic demo data written to {OUT}")


if __name__ == "__main__":
    main()
