from __future__ import annotations

from datetime import timedelta
from itertools import combinations
from typing import Sequence

from .explain import format_date
from .forecast import Baseline
from .ledger import lowest, simulate
from .models import Candidate, Capacity, Case, Payment, Series, SpendingChange
from .money import ZERO, display

MAX_CHANGES = 3


def base_candidates(case: Case, capacity: Capacity) -> list[Candidate]:
    profile, request = case.profile, case.request
    today = request.created_on
    accepted = profile.accepted_methods
    candidates: list[Candidate] = []

    if "full_payment" in accepted:
        candidates.append(Candidate("full_payment", (Payment(today, request.amount),), request.amount))
        earliest = capacity.earliest_full
        if earliest is not None and earliest > today:
            wait = Candidate("wait", (Payment(earliest, request.amount),), request.amount)
            if earliest > request.deadline:
                wait.rejection = "Full payment only becomes safe after the deadline"
            candidates.append(wait)

    if (
        "partial_payment" in accepted
        and request.allows_partial
        and ZERO < capacity.safe_today < request.amount
        and capacity.earliest_full is not None
        and capacity.earliest_full <= request.deadline
    ):
        candidates.append(
            Candidate(
                "partial_payment",
                (
                    Payment(today, capacity.safe_today),
                    Payment(capacity.earliest_full, request.amount - capacity.safe_today),
                ),
                request.amount,
            )
        )

    if "installments" in accepted:
        for option in sorted(request.options, key=lambda item: item.option_id):
            payments = tuple(
                Payment(option.first_date + timedelta(days=option.interval_days * index), option.installment_amount)
                for index in range(option.count)
            )
            candidate = Candidate("installments", payments, option.total, option.option_id)
            if profile.max_installments is not None and option.count > profile.max_installments:
                candidate.rejection = (
                    f"{option.count} payments exceeds the limit of {profile.max_installments}"
                )
            elif sum((payment.amount for payment in payments), ZERO) < request.amount:
                candidate.rejection = "Plan pays less than the requested amount"
            elif payments[-1].on > request.deadline:
                candidate.rejection = "Final installment falls after the deadline"
            elif payments[0].on < today:
                candidate.rejection = "Schedule starts before the request date"
            candidates.append(candidate)
    return candidates


def eligible_changes(case: Case, series: Sequence[Series]) -> list[SpendingChange]:
    profile = case.profile
    changes: list[SpendingChange] = []
    for item in series:
        if item.direction != "out" or item.category in profile.protected_categories:
            continue
        if item.category in profile.stoppable_categories and item.flexibility in {"stoppable", "reducible_or_stoppable"}:
            changes.append(
                SpendingChange("stop", item.series_id, item.last_transaction_id, item.label, item.currency, item.amount, ZERO)
            )
        if item.category in profile.reducible_categories and item.flexibility in {"reducible", "reducible_or_stoppable"}:
            target = item.minimum_amount if item.minimum_amount is not None else ZERO
            if target < item.amount:
                changes.append(
                    SpendingChange("reduce", item.series_id, item.last_transaction_id, item.label, item.currency, item.amount, target)
                )
    return changes


def verify(candidate: Candidate, case: Case, baseline: Baseline) -> None:
    if candidate.rejection:
        candidate.safe = False
        return
    if candidate.payments[-1].on > baseline.end:
        candidate.safe = False
        candidate.rejection = "Plan runs past the 90-day forecast"
        return
    profile = case.profile
    points = simulate(
        profile.balance, baseline.as_of, baseline.horizon_days, baseline.flows,
        candidate.payments, candidate.changes,
    )
    day, balance = lowest(points)
    candidate.lowest_balance = balance
    candidate.lowest_on = day
    candidate.safe = balance >= profile.minimum_balance
    if not candidate.safe:
        candidate.rejection = (
            f"Balance falls to {display(balance, profile.currency)} on {format_date(day)}, "
            f"below the {display(profile.minimum_balance, profile.currency)} minimum"
        )


def rank_key(candidate: Candidate) -> tuple[object, ...]:
    reduction = sum((change.current_amount - change.new_amount for change in candidate.changes), ZERO)
    return (
        len(candidate.changes),
        reduction,
        candidate.total,
        candidate.payments[0].on,
        len(candidate.payments),
        candidate.option_id or "",
    )


def choose(case: Case, baseline: Baseline, capacity: Capacity) -> tuple[Candidate | None, list[Candidate]]:
    candidates = base_candidates(case, capacity)
    for candidate in candidates:
        verify(candidate, case, baseline)
    safe = [candidate for candidate in candidates if candidate.safe]
    if safe:
        return min(safe, key=rank_key), candidates

    options = eligible_changes(case, baseline.series)
    for size in range(1, min(MAX_CHANGES, len(options)) + 1):
        found: list[Candidate] = []
        for combo in combinations(options, size):
            if len({change.series_id for change in combo}) < size:
                continue
            for base in base_candidates(case, capacity):
                if base.rejection:
                    continue
                changed = Candidate(base.method, base.payments, base.total, base.option_id, combo)
                verify(changed, case, baseline)
                if changed.safe:
                    found.append(changed)
        if found:
            best = min(found, key=rank_key)
            return best, candidates + [best]
    return None, candidates
