from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import calendar

import numpy as np
from scipy.optimize import brentq


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def shift_months(d: date, months: int) -> date:
    month0 = d.month - 1 + months
    year = d.year + month0 // 12
    month = month0 % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def day_count_30_360_us(start: date | str, end: date | str) -> int:
    """US/NASD 30/360 day count for the fixed-rate periods used here."""
    d1 = _as_date(start)
    d2 = _as_date(end)
    d1_day = 30 if d1.day == 31 else d1.day
    d2_day = d2.day
    if d2_day == 31 and d1_day >= 30:
        d2_day = 30
    return 360 * (d2.year - d1.year) + 30 * (d2.month - d1.month) + (d2_day - d1_day)


@dataclass(frozen=True)
class FixedToFloatBond:
    issuer: str
    cusip: str
    coupon_rate: float
    issue_date: date
    first_par_call_date: date
    maturity_date: date
    coupon_frequency: int = 2
    par: float = 100.0

    @classmethod
    def from_dict(cls, x: dict) -> "FixedToFloatBond":
        return cls(
            issuer=x["issuer"],
            cusip=x["cusip"],
            coupon_rate=float(x["coupon_rate"]),
            issue_date=_as_date(x["issue_date"]),
            first_par_call_date=_as_date(x["first_par_call_date"]),
            maturity_date=_as_date(x["maturity_date"]),
            coupon_frequency=int(x.get("coupon_frequency", 2)),
        )


def fixed_coupon_dates_to_call(bond: FixedToFloatBond) -> list[date]:
    months = 12 // bond.coupon_frequency
    dates: list[date] = []
    d = bond.first_par_call_date
    while d > bond.issue_date:
        dates.append(d)
        d = shift_months(d, -months)
    return sorted(dates)


def coupon_bracket(bond: FixedToFloatBond, settlement: date | str) -> tuple[date, date]:
    settlement = _as_date(settlement)
    dates = fixed_coupon_dates_to_call(bond)
    if settlement >= bond.first_par_call_date:
        raise ValueError("Settlement is on/after first par call; fixed-period YTC proxy no longer applies")
    prior = bond.issue_date
    for d in dates:
        if d <= settlement:
            prior = d
            continue
        return prior, d
    raise ValueError("Could not locate next coupon date")


def accrued_interest_per_100(bond: FixedToFloatBond, settlement: date | str) -> float:
    settlement = _as_date(settlement)
    prior, nxt = coupon_bracket(bond, settlement)
    coupon = bond.par * bond.coupon_rate / bond.coupon_frequency
    period_days = day_count_30_360_us(prior, nxt)
    accrued_days = day_count_30_360_us(prior, settlement)
    fraction = 0.0 if period_days <= 0 else max(0.0, min(1.0, accrued_days / period_days))
    return coupon * fraction


def dirty_price_from_ytc(bond: FixedToFloatBond, settlement: date | str, ytc_decimal: float) -> float:
    settlement = _as_date(settlement)
    prior, nxt = coupon_bracket(bond, settlement)
    dates = [d for d in fixed_coupon_dates_to_call(bond) if d > settlement]
    if not dates:
        raise ValueError("No fixed-rate cash flows remain before call")

    coupon = bond.par * bond.coupon_rate / bond.coupon_frequency
    period_days = day_count_30_360_us(prior, nxt)
    days_to_next = day_count_30_360_us(settlement, nxt)
    w = days_to_next / period_days
    per_period = ytc_decimal / bond.coupon_frequency
    if 1.0 + per_period <= 0:
        return np.inf

    pv = 0.0
    for j, d in enumerate(dates):
        cf = coupon + (bond.par if d == bond.first_par_call_date else 0.0)
        pv += cf / (1.0 + per_period) ** (w + j)
    return pv


def clean_price_from_ytc(bond: FixedToFloatBond, settlement: date | str, ytc_decimal: float) -> float:
    return dirty_price_from_ytc(bond, settlement, ytc_decimal) - accrued_interest_per_100(bond, settlement)


def yield_to_call_from_clean_price(bond: FixedToFloatBond, settlement: date | str, clean_price: float) -> float:
    """Nominal annual YTC with compounding at coupon frequency; returned as decimal."""
    settlement = _as_date(settlement)
    target_dirty = float(clean_price) + accrued_interest_per_100(bond, settlement)

    def f(y: float) -> float:
        return dirty_price_from_ytc(bond, settlement, y) - target_dirty

    return float(brentq(f, -0.50, 2.00, maxiter=200))
