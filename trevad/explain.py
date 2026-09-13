from __future__ import annotations

from datetime import date
from typing import Optional, Sequence

from .models import Candidate, Capacity, Case, SpendingChange
from .money import display


def format_date(value: date) -> str:
    return f"{value.day} {value.strftime('%B %Y')}"


def describe_changes(changes: Sequence[SpendingChange], currency: str) -> str:
    parts = []
    for change in changes:
        if change.action == "stop":
            parts.append(f"stop {change.label}")
        else:
            parts.append(f"reduce {change.label} to {display(change.new_amount, currency)}")
    return " and ".join(parts)


def explain(case: Case, capacity: Capacity, selected: Optional[Candidate]) -> str:
    profile, request = case.profile, case.request
    currency = profile.currency
    amount = display(request.amount, currency)
    minimum = display(profile.minimum_balance, currency)

    if selected is None:
        text = (
            f"Not recommended. No available way to pay {amount} by {format_date(request.deadline)} "
            f"keeps your balance above the {minimum} minimum."
        )
        if capacity.earliest_full is not None:
            text += f" A full payment only becomes safe on {format_date(capacity.earliest_full)}."
        elif capacity.safe_today > 0:
            text += f" At most {display(capacity.safe_today, currency)} is safe to pay today."
        return text

    first = selected.payments[0]
    lowest = display(selected.lowest_balance, currency) if selected.lowest_balance is not None else minimum
    if selected.method == "full_payment":
        text = f"Pay {amount} today. Your balance stays at or above {lowest} for the next 90 days."
    elif selected.method == "wait":
        text = (
            f"Wait until {format_date(first.on)}, then pay {amount} in full. "
            f"Paying earlier would take your balance below the {minimum} minimum."
        )
    elif selected.method == "partial_payment":
        second = selected.payments[1]
        text = (
            f"Pay {display(first.amount, currency)} today and {display(second.amount, currency)} "
            f"on {format_date(second.on)}. Both payments keep your balance above the {minimum} minimum."
        )
    else:
        text = (
            f"Use the {len(selected.payments)}-payment plan of {display(first.amount, currency)} "
            f"starting {format_date(first.on)}, {display(selected.total, currency)} in total. "
            f"Your balance stays at or above {lowest}."
        )
    if selected.changes:
        text += f" This only works if you {describe_changes(selected.changes, currency)}."
    return text
