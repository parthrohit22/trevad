from __future__ import annotations

from typing import Optional

from .explain import explain
from .forecast import HORIZON_DAYS, build_baseline
from .ledger import capacity, simulate
from .models import Candidate, Case, Decision
from .planner import choose


def verdict_for(selected: Optional[Candidate]) -> str:
    if selected is None:
        return "not_affordable"
    if selected.method == "wait":
        return "affordable_later"
    if selected.method == "full_payment" and not selected.changes:
        return "affordable_now"
    return "affordable_with_plan"


def decide(case: Case, horizon_days: int = HORIZON_DAYS) -> Decision:
    profile, request = case.profile, case.request
    baseline = build_baseline(case, horizon_days)
    baseline_points = simulate(profile.balance, baseline.as_of, horizon_days, baseline.flows)
    result = capacity(profile.minimum_balance, request.amount, baseline_points)
    selected, candidates = choose(case, baseline, result)

    if selected is None:
        plan_points = baseline_points
    else:
        plan_points = simulate(
            profile.balance, baseline.as_of, horizon_days, baseline.flows,
            selected.payments, selected.changes,
        )

    return Decision(
        request_id=request.request_id,
        user_id=profile.user_id,
        currency=profile.currency,
        requested_amount=request.amount,
        minimum_balance=profile.minimum_balance,
        safe_to_pay_today=result.safe_today,
        verdict=verdict_for(selected),
        method=selected.method if selected else "not_recommended",
        schedule=selected.payments if selected else (),
        option_id=selected.option_id if selected else None,
        earliest_full_payment_date=result.earliest_full,
        spending_changes=selected.changes if selected else (),
        explanation=explain(case, result, selected),
        baseline_forecast=baseline_points,
        plan_forecast=plan_points,
        candidates=tuple(candidates),
        facts=baseline.facts,
        flows=baseline.flows,
    )
