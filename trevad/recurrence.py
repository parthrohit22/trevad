from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Iterator, Sequence

from .models import Series, Transaction
from .money import add_months

MIN_OCCURRENCES = 3
WEEKLY_INTERVALS = frozenset({7, 14})
INCOME_VARIATION_LIMIT = Decimal("1.05")
EXCLUDED_KINDS = frozenset({"refund", "transfer", "investment"})
IRREGULAR_INCOME_WORDS = (
    "bonus", "commission", "reimbursement", "refund", "prize", "gift", "arrears", "tip",
)


def series_key(transaction: Transaction) -> str:
    label = re.sub(r"[\d#/-]+", " ", transaction.description.lower())
    label = re.sub(r"\s+", " ", label).strip()
    return f"{transaction.direction}:{transaction.category}:{transaction.currency}:{label}"


def _eligible(transaction: Transaction, as_of: date) -> bool:
    if transaction.status != "settled" or transaction.date > as_of:
        return False
    if transaction.kind in EXCLUDED_KINDS:
        return False
    if transaction.direction == "in":
        text = transaction.description.lower()
        return not any(word in text for word in IRREGULAR_INCOME_WORDS)
    return True


def _rhythm(dates: Sequence[date]) -> tuple[bool, int | None] | None:
    recent = dates[-6:]
    days = [min(item.day, 28) for item in recent]
    if max(days) - min(days) <= 2:
        gaps = [(later - earlier).days for earlier, later in zip(recent, recent[1:])]
        if all(26 <= gap <= 35 for gap in gaps):
            return True, None
    intervals = [(later - earlier).days for earlier, later in zip(recent, recent[1:])]
    if not intervals:
        return None
    interval, frequency = Counter(intervals).most_common(1)[0]
    if interval not in WEEKLY_INTERVALS or frequency < max(2, len(intervals) // 2):
        return None
    return False, interval


def occurrences(series: Series, after: date, until: date) -> Iterator[date]:
    step = 1
    while True:
        if series.monthly:
            current = add_months(series.last_date, step)
        else:
            current = series.last_date + timedelta(days=(series.interval_days or 30) * step)
        if current > until:
            return
        if current > after:
            yield current
        step += 1


def _is_active(series: Series, as_of: date) -> bool:
    grace = timedelta(days=(series.interval_days or 31) * 2)
    return series.last_date + grace >= as_of


def detect_series(transactions: Iterable[Transaction], as_of: date) -> list[Series]:
    groups: dict[str, list[Transaction]] = defaultdict(list)
    for transaction in transactions:
        if _eligible(transaction, as_of):
            groups[series_key(transaction)].append(transaction)

    detected: list[Series] = []
    for key, rows in sorted(groups.items()):
        rows.sort(key=lambda item: (item.date, item.transaction_id))
        if len(rows) < MIN_OCCURRENCES:
            continue
        rhythm = _rhythm([row.date for row in rows])
        if rhythm is None:
            continue
        monthly, interval = rhythm
        latest = rows[-1]
        recent = [row.amount for row in rows[-3:]]
        if latest.direction == "in":
            window = [row.amount for row in rows[-5:]]
            if max(window) > min(window) * INCOME_VARIATION_LIMIT:
                continue
            if "final" in latest.description.lower():
                continue
            amount = min(recent)
        else:
            amount = max(recent)
        series = Series(
            series_id=key,
            label=latest.description,
            category=latest.category,
            direction=latest.direction,
            currency=latest.currency,
            amount=amount,
            monthly=monthly,
            interval_days=interval,
            last_date=latest.date,
            last_transaction_id=latest.transaction_id,
            flexibility=latest.flexibility,
            minimum_amount=latest.minimum_amount,
        )
        if _is_active(series, as_of):
            detected.append(series)
    return detected
