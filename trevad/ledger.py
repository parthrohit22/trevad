from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Sequence

from .models import Capacity, Flow, Payment, SpendingChange
from .money import ZERO, round_down

Points = tuple[tuple[date, Decimal], ...]


def simulate(
    opening: Decimal,
    start: date,
    horizon_days: int,
    flows: Sequence[Flow],
    payments: Sequence[Payment] = (),
    changes: Sequence[SpendingChange] = (),
) -> Points:
    ratios: dict[str, Decimal] = {}
    for change in changes:
        if change.action == "stop" or change.current_amount <= ZERO:
            ratios[change.series_id] = ZERO
        else:
            ratios[change.series_id] = change.new_amount / change.current_amount

    daily: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for flow in flows:
        amount = flow.amount
        if flow.source == "projected" and flow.direction == "out" and flow.series_id in ratios:
            amount = amount * ratios[flow.series_id]
        daily[flow.on] += amount if flow.direction == "in" else -amount
    for payment in payments:
        daily[payment.on] -= payment.amount

    balance = opening
    points: list[tuple[date, Decimal]] = []
    for offset in range(horizon_days + 1):
        current = start + timedelta(days=offset)
        balance += daily.get(current, ZERO)
        points.append((current, balance))
    return tuple(points)


def lowest(points: Points) -> tuple[date, Decimal]:
    day, balance = min(points, key=lambda point: (point[1], point[0]))
    return day, balance


def capacity(minimum_balance: Decimal, amount: Decimal, points: Points) -> Capacity:
    suffix: list[tuple[date, Decimal]] = []
    running: Decimal | None = None
    for day, balance in reversed(points):
        running = balance if running is None else min(running, balance)
        suffix.append((day, running))
    suffix.reverse()
    headroom = suffix[0][1] - minimum_balance
    safe_today = round_down(min(amount, max(ZERO, headroom)))
    earliest = next((day for day, low in suffix if low - minimum_balance >= amount), None)
    return Capacity(safe_today=safe_today, earliest_full=earliest, balances=points)
