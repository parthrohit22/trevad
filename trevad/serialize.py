from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .models import Case, Decision, Payment, SpendingChange
from .money import round_down

CSV_COLUMNS = (
    "request_id", "user_id", "currency", "requested_amount", "safe_to_pay_today", "verdict",
    "method", "schedule", "earliest_full_payment_date", "spending_changes", "explanation",
)


def money(value) -> Optional[str]:
    return None if value is None else f"{round_down(value):.2f}"


def _payment(payment: Payment) -> Dict[str, Any]:
    return {"date": payment.on.isoformat(), "amount": money(payment.amount)}


def _change(change: SpendingChange) -> Dict[str, Any]:
    return {
        "action": change.action,
        "transaction_id": change.transaction_id,
        "label": change.label,
        "current_amount": money(change.current_amount),
        "new_amount": money(change.new_amount),
    }


def decision_to_dict(decision: Decision, case: Optional[Case] = None, detail: bool = True) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "request_id": decision.request_id,
        "user_id": decision.user_id,
        "currency": decision.currency,
        "requested_amount": money(decision.requested_amount),
        "minimum_balance": money(decision.minimum_balance),
        "safe_to_pay_today": money(decision.safe_to_pay_today),
        "verdict": decision.verdict,
        "method": decision.method,
        "schedule": [_payment(payment) for payment in decision.schedule],
        "option_id": decision.option_id,
        "earliest_full_payment_date": (
            decision.earliest_full_payment_date.isoformat() if decision.earliest_full_payment_date else None
        ),
        "spending_changes": [_change(change) for change in decision.spending_changes],
        "explanation": decision.explanation,
    }
    if case is not None:
        result["request"] = {
            "title": case.request.title,
            "category": case.request.category,
            "created_on": case.request.created_on.isoformat(),
            "deadline": case.request.deadline.isoformat(),
            "allows_partial": case.request.allows_partial,
            "user_name": case.profile.name,
            "balance": money(case.profile.balance),
            "accepted_methods": sorted(case.profile.accepted_methods),
        }
    if not detail:
        return result
    result["forecast"] = [
        {"date": day.isoformat(), "baseline": money(base), "with_plan": money(planned)}
        for (day, base), (_, planned) in zip(decision.baseline_forecast, decision.plan_forecast)
    ]
    result["candidates"] = [
        {
            "method": candidate.method,
            "option_id": candidate.option_id,
            "total": money(candidate.total),
            "payments": [_payment(payment) for payment in candidate.payments],
            "changes": [_change(change) for change in candidate.changes],
            "safe": candidate.safe,
            "lowest_balance": money(candidate.lowest_balance),
            "lowest_on": candidate.lowest_on.isoformat() if candidate.lowest_on else None,
            "rejection": candidate.rejection,
        }
        for candidate in decision.candidates
    ]
    result["evidence"] = [
        {"kind": fact.kind, "message_id": fact.message_id, "summary": fact.summary, "transaction_id": fact.transaction_id}
        for fact in decision.facts
    ]
    result["cash_flows"] = [
        {
            "date": flow.on.isoformat(),
            "direction": flow.direction,
            "amount": money(flow.amount),
            "category": flow.category,
            "label": flow.label,
            "source": flow.source,
            "reference": flow.reference,
        }
        for flow in decision.flows
    ]
    return result


def csv_row(decision: Decision) -> Dict[str, str]:
    changes = []
    for change in decision.spending_changes:
        if change.action == "stop":
            changes.append(f"stop:{change.transaction_id}")
        else:
            changes.append(f"reduce:{change.transaction_id}:{money(change.new_amount)}")
    return {
        "request_id": decision.request_id,
        "user_id": decision.user_id,
        "currency": decision.currency,
        "requested_amount": money(decision.requested_amount),
        "safe_to_pay_today": money(decision.safe_to_pay_today),
        "verdict": decision.verdict,
        "method": decision.method,
        "schedule": "|".join(f"{p.on.isoformat()}:{money(p.amount)}" for p in decision.schedule) or "none",
        "earliest_full_payment_date": (
            decision.earliest_full_payment_date.isoformat() if decision.earliest_full_payment_date else ""
        ),
        "spending_changes": "|".join(changes) or "none",
        "explanation": decision.explanation,
    }


def write_csv(path: Path, decisions: Sequence[Decision]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(csv_row(decision) for decision in decisions)
    temporary.replace(path)


def write_json(path: Path, decisions: Sequence[Decision], cases: Sequence[Case]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [decision_to_dict(decision, case, detail=False) for decision, case in zip(decisions, cases)]
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
