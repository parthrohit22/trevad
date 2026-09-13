from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import Iterable

from .errors import DataError
from .models import FxRate

ZERO = Decimal("0")
CENT = Decimal("0.01")


def to_decimal(value: str | int | float | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value).replace(",", "").strip())


def round_down(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_DOWN)


def display(value: Decimal, currency: str | None = None) -> str:
    rounded = round_down(value)
    text = f"{rounded:,.2f}"
    if text.endswith(".00"):
        text = text[:-3]
    return f"{currency} {text}" if currency else text


def add_months(value: date, months: int = 1) -> date:
    index = value.month - 1 + months
    year = value.year + index // 12
    month = index % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


class FxTable:
    def __init__(self, rates: Iterable[FxRate]) -> None:
        self._rates: dict[tuple[str, str], list[tuple[date, Decimal]]] = {}
        for rate in rates:
            self._rates.setdefault((rate.base, rate.quote), []).append((rate.on, rate.rate))
        for series in self._rates.values():
            series.sort()

    def _lookup(self, base: str, quote: str, on: date) -> Decimal | None:
        series = self._rates.get((base, quote))
        if not series:
            return None
        applicable = [rate for rate_date, rate in series if rate_date <= on]
        return applicable[-1] if applicable else series[0][1]

    def convert(self, amount: Decimal, source: str, target: str, on: date) -> Decimal:
        if source == target:
            return amount
        direct = self._lookup(source, target, on)
        if direct is not None:
            return amount * direct
        inverse = self._lookup(target, source, on)
        if inverse is not None:
            return amount / inverse
        raise DataError(f"No exchange rate available for {source} to {target} on {on.isoformat()}")
