from __future__ import annotations

from datetime import timedelta
from typing import List

from .errors import ContractError
from .forecast import HORIZON_DAYS
from .models import Case, Decision
from .money import ZERO

VERDICTS = {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}
METHODS = {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}
IMMEDIATE_METHODS = {"full_payment", "partial_payment", "installments"}


def find_problems(case: Case, decision: Decision, horizon_days: int = HORIZON_DAYS) -> List[str]:
    profile, request = case.profile, case.request
    problems: List[str] = []
    schedule = list(decision.schedule)
    total = sum((payment.amount for payment in schedule), ZERO)
    method, verdict = decision.method, decision.verdict
    earliest = decision.earliest_full_payment_date

    if verdict not in VERDICTS:
        problems.append(f"unknown verdict {verdict}")
    if method not in METHODS:
        problems.append(f"unknown method {method}")
    if not ZERO <= decision.safe_to_pay_today <= request.amount:
        problems.append("safe amount is outside zero and the requested amount")
    if not decision.explanation.strip():
        problems.append("explanation is empty")
    if any(payment.amount <= ZERO for payment in schedule):
        problems.append("every payment must be positive")
    if [payment.on for payment in schedule] != sorted(payment.on for payment in schedule):
        problems.append("payments must be in date order")
    if schedule and schedule[0].on < request.created_on:
        problems.append("a payment is dated before the request")
    if schedule and schedule[-1].on > request.deadline:
        problems.append("the plan finishes after the deadline")
    if schedule and schedule[-1].on > request.created_on + timedelta(days=horizon_days):
        problems.append("the plan runs past the forecast window")
    if earliest is not None and not request.created_on <= earliest <= request.created_on + timedelta(days=horizon_days):
        problems.append("earliest full payment date is outside the forecast")

    if method in IMMEDIATE_METHODS and method not in profile.accepted_methods:
        problems.append(f"the user does not accept {method}")

    if method == "not_recommended":
        if verdict != "not_affordable" or schedule or decision.spending_changes:
            problems.append("not_recommended must have no plan and no changes")
    elif verdict == "not_affordable":
        problems.append("not_affordable must use not_recommended")

    if method == "full_payment":
        if len(schedule) != 1 or schedule[0].on != request.created_on or total != request.amount:
            problems.append("full payment must be the whole amount today")
    if verdict == "affordable_now":
        if method != "full_payment" or decision.spending_changes or earliest != request.created_on:
            problems.append("affordable_now must be a full payment today with no changes")

    if method == "wait":
        if "full_payment" not in profile.accepted_methods:
            problems.append("wait requires the user to accept full payment")
        if verdict != "affordable_later":
            problems.append("wait must be affordable_later")
        if len(schedule) != 1 or total != request.amount or schedule[0].on != earliest:
            problems.append("wait must be one full payment on the earliest safe date")

    if method == "partial_payment":
        if not request.allows_partial:
            problems.append("this request does not allow partial payment")
        if (
            len(schedule) != 2
            or schedule[0].on != request.created_on
            or schedule[0].amount != decision.safe_to_pay_today
            or schedule[1].on != earliest
            or total != request.amount
        ):
            problems.append("partial payment must be the safe amount today and the rest on the earliest safe date")

    if method == "installments":
        option = next((item for item in request.options if item.option_id == decision.option_id), None)
        if option is None:
            problems.append("installment plan does not match a supplied option")
        else:
            expected = [
                (option.first_date + timedelta(days=option.interval_days * index), option.installment_amount)
                for index in range(option.count)
            ]
            if [(payment.on, payment.amount) for payment in schedule] != expected:
                problems.append("installment schedule differs from the supplied option")
            if total < request.amount:
                problems.append("installments pay less than the requested amount")
            if profile.max_installments is not None and option.count > profile.max_installments:
                problems.append("installment count is above the user's limit")

    changes = decision.spending_changes
    if len(changes) > 3:
        problems.append("more than three spending changes")
    if len({change.series_id for change in changes}) != len(changes):
        problems.append("the same expense is changed twice")
    transactions = {item.transaction_id: item for item in case.transactions}
    for change in changes:
        source = transactions.get(change.transaction_id)
        if source is None:
            problems.append(f"change refers to unknown transaction {change.transaction_id}")
            continue
        if source.category in profile.protected_categories:
            problems.append(f"{source.category} is protected")
        if change.action == "stop":
            if source.category not in profile.stoppable_categories or source.flexibility not in {"stoppable", "reducible_or_stoppable"}:
                problems.append(f"{change.label} cannot be stopped")
        else:
            floor = source.minimum_amount if source.minimum_amount is not None else ZERO
            if source.category not in profile.reducible_categories or source.flexibility not in {"reducible", "reducible_or_stoppable"}:
                problems.append(f"{change.label} cannot be reduced")
            if not floor <= change.new_amount < change.current_amount:
                problems.append(f"{change.label} reduction is outside the allowed range")
    return problems


def ensure_valid(case: Case, decision: Decision) -> None:
    problems = find_problems(case, decision)
    if problems:
        raise ContractError(f"{decision.request_id}: " + "; ".join(problems))
