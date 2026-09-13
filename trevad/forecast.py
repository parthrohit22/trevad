from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Sequence

from .evidence import extract_facts
from .models import Case, Fact, Flow, Series, Transaction
from .money import FxTable
from .recurrence import detect_series, occurrences, series_key

HORIZON_DAYS = 90
MATCH_WINDOW_DAYS = 7
INCOME_CATEGORIES = frozenset({"salary", "wages", "payroll"})
STATUS_PRIORITY = {"settled": 0, "scheduled": 1, "pending": 2, "failed": 3, "cancelled": 4, "unrealized": 5}


@dataclass(frozen=True)
class Baseline:
    as_of: date
    end: date
    horizon_days: int
    flows: tuple[Flow, ...]
    series: tuple[Series, ...]
    facts: tuple[Fact, ...]
    fx: FxTable


def deduplicate(transactions: Iterable[Transaction]) -> list[Transaction]:
    seen: set[tuple[object, ...]] = set()
    kept: list[Transaction] = []
    ordered = sorted(
        transactions,
        key=lambda item: (STATUS_PRIORITY.get(item.status, 9), item.transaction_id),
    )
    for transaction in ordered:
        key = (
            transaction.direction, transaction.category, transaction.amount, transaction.currency,
            transaction.date, transaction.description.strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        kept.append(transaction)
    return sorted(kept, key=lambda item: (item.date, item.transaction_id))


def _apply_transaction_facts(
    transactions: Sequence[Transaction], facts: Sequence[Fact], as_of: date
) -> list[Transaction]:
    by_id = {item.transaction_id: item for item in transactions}
    for fact in facts:
        if fact.transaction_id is None or fact.transaction_id not in by_id:
            continue
        current = by_id[fact.transaction_id]
        if fact.kind == "transaction_cancelled":
            by_id[current.transaction_id] = replace(current, status="cancelled")
        elif fact.kind == "transaction_moved" and fact.on is not None and current.status != "settled":
            by_id[current.transaction_id] = replace(current, date=fact.on)
        elif fact.kind == "transaction_amended" and fact.amount is not None:
            by_id[current.transaction_id] = replace(
                current, amount=fact.amount, currency=fact.currency or current.currency
            )
        elif fact.kind == "bill_outstanding" and current.status == "failed" and current.direction == "out":
            due = max(current.date, fact.on or as_of, as_of)
            by_id[current.transaction_id] = replace(current, status="pending", date=due)
    return sorted(by_id.values(), key=lambda item: (item.date, item.transaction_id))


def _scheduled_flows(
    transactions: Sequence[Transaction], as_of: date, end: date, fx: FxTable, currency: str
) -> list[Flow]:
    flows: list[Flow] = []
    for transaction in transactions:
        if transaction.status in {"pending", "scheduled"}:
            if transaction.direction == "in" and transaction.status == "pending":
                continue
            if transaction.direction == "in" and transaction.date <= as_of:
                continue
            on = max(transaction.date, as_of)
        elif transaction.status == "settled" and transaction.date > as_of:
            on = transaction.date
        else:
            continue
        if on > end:
            continue
        flows.append(
            Flow(
                on=on,
                amount=fx.convert(transaction.amount, transaction.currency, currency, on),
                direction=transaction.direction,
                category=transaction.category,
                label=transaction.description,
                source="scheduled",
                reference=transaction.transaction_id,
                series_id=series_key(transaction),
            )
        )
    return flows


def _adjusted(series: Series, on: date, facts: Sequence[Fact]) -> tuple[Decimal, str]:
    amount, currency = series.amount, series.currency
    for fact in facts:
        effective = fact.on is None or on >= fact.on
        if not effective:
            continue
        if (
            fact.kind == "income_changed"
            and series.direction == "in"
            and series.category in INCOME_CATEGORIES
            and fact.amount is not None
        ):
            amount, currency = fact.amount, fact.currency or currency
        elif (
            fact.kind == "expense_changed"
            and series.direction == "out"
            and series.category == fact.category
            and fact.percent is not None
        ):
            amount = amount * (Decimal("1") + fact.percent / Decimal("100"))
    return amount, currency


def _covered(series: Series, on: date, scheduled: Sequence[Flow]) -> bool:
    for flow in scheduled:
        if flow.direction != series.direction:
            continue
        if abs((flow.on - on).days) > MATCH_WINDOW_DAYS:
            continue
        if flow.series_id == series.series_id:
            return True
        if series.category in INCOME_CATEGORIES and flow.category == series.category:
            return True
    return False


def _projected_flows(
    series: Sequence[Series],
    facts: Sequence[Fact],
    scheduled: Sequence[Flow],
    as_of: date,
    end: date,
    fx: FxTable,
    currency: str,
) -> list[Flow]:
    flows: list[Flow] = []
    for item in series:
        for on in occurrences(item, as_of - timedelta(days=1), end):
            if on < as_of or _covered(item, on, scheduled):
                continue
            amount, source_currency = _adjusted(item, on, facts)
            flows.append(
                Flow(
                    on=on,
                    amount=fx.convert(amount, source_currency, currency, on),
                    direction=item.direction,
                    category=item.category,
                    label=item.label,
                    source="projected",
                    reference=item.last_transaction_id,
                    series_id=item.series_id,
                )
            )
    return flows


def _apply_flow_facts(
    flows: list[Flow], facts: Sequence[Fact], as_of: date, end: date, fx: FxTable, currency: str
) -> list[Flow]:
    for fact in facts:
        if fact.kind == "income_ended":
            cutoff = fact.on or as_of
            flows = [
                flow for flow in flows
                if not (flow.direction == "in" and flow.category in INCOME_CATEGORIES and flow.on >= cutoff)
            ]
        elif fact.kind == "income_moved" and fact.on is not None and fact.on >= as_of:
            upcoming = [
                flow for flow in flows
                if flow.direction == "in" and flow.category in INCOME_CATEGORIES and flow.on >= as_of
            ]
            if upcoming:
                first = min(upcoming, key=lambda flow: flow.on)
                flows.remove(first)
                if fact.on <= end:
                    flows.append(replace(first, on=fact.on, source="evidence", reference=fact.message_id))
        elif (
            fact.kind == "one_time_income"
            and fact.on is not None
            and fact.amount is not None
            and as_of <= fact.on <= end
        ):
            flows.append(
                Flow(
                    on=fact.on,
                    amount=fx.convert(fact.amount, fact.currency or currency, currency, fact.on),
                    direction="in",
                    category="one_time_income",
                    label="Confirmed one-time income",
                    source="evidence",
                    reference=fact.message_id,
                )
            )
    return flows


def build_baseline(case: Case, horizon_days: int = HORIZON_DAYS) -> Baseline:
    profile, request = case.profile, case.request
    as_of = request.created_on
    end = as_of + timedelta(days=horizon_days)
    fx = FxTable(case.fx_rates)

    transactions = deduplicate(case.transactions)
    facts = extract_facts(case.messages, {item.transaction_id: item for item in transactions}, as_of)
    transactions = _apply_transaction_facts(transactions, facts, as_of)
    series = detect_series(transactions, as_of)

    scheduled = _scheduled_flows(transactions, as_of, end, fx, profile.currency)
    projected = _projected_flows(series, facts, scheduled, as_of, end, fx, profile.currency)
    flows = _apply_flow_facts(scheduled + projected, facts, as_of, end, fx, profile.currency)
    flows.sort(key=lambda flow: (flow.on, flow.direction, flow.label))

    return Baseline(
        as_of=as_of,
        end=end,
        horizon_days=horizon_days,
        flows=tuple(flows),
        series=tuple(series),
        facts=tuple(facts),
        fx=fx,
    )
