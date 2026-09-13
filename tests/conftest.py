from __future__ import annotations

import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trevad.models import Case, Profile, PurchaseRequest, Transaction
from trevad.money import add_months

TODAY = date(2026, 3, 10)


def money(value) -> Decimal:
    return Decimal(str(value))


def monthly(prefix, description, category, direction, amount, day, months=6, flexibility="fixed", minimum=None, currency="USD"):
    last = date(TODAY.year, TODAY.month, day)
    if last > TODAY:
        last = add_months(last, -1)
    rows = []
    for index in range(months):
        rows.append(
            Transaction(
                transaction_id=f"{prefix}-{index + 1}",
                user_id="u1",
                description=description,
                category=category,
                direction=direction,
                amount=money(amount),
                currency=currency,
                date=add_months(last, index - months + 1),
                status="settled",
                kind="regular",
                flexibility=flexibility,
                minimum_amount=money(minimum) if minimum is not None else None,
            )
        )
    return rows


def one_off(transaction_id, amount, on, status="pending", direction="out", description="Card charge", category="shopping"):
    return Transaction(
        transaction_id=transaction_id,
        user_id="u1",
        description=description,
        category=category,
        direction=direction,
        amount=money(amount),
        currency="USD",
        date=on,
        status=status,
        kind="one_time",
    )


def build_case(
    balance=3000,
    minimum=1000,
    amount=1500,
    deadline_days=60,
    accepted=("full_payment",),
    allows_partial=False,
    options=(),
    extra=(),
    messages=(),
    salary=3000,
    salary_day=25,
    salary_currency="USD",
    rent=1200,
    rent_day=15,
    protected=("rent",),
    reducible=(),
    stoppable=(),
    max_installments=None,
    fx_rates=(),
):
    profile = Profile(
        user_id="u1",
        name="Test User",
        currency="USD",
        balance=money(balance),
        minimum_balance=money(minimum),
        protected_categories=frozenset(protected),
        reducible_categories=frozenset(reducible),
        stoppable_categories=frozenset(stoppable),
        accepted_methods=frozenset(accepted),
        max_installments=max_installments,
    )
    transactions = []
    if salary:
        transactions += monthly("salary", "Payroll", "salary", "in", salary, salary_day, currency=salary_currency)
    if rent:
        transactions += monthly("rent", "Apartment rent", "rent", "out", rent, rent_day)
    transactions += list(extra)
    request = PurchaseRequest(
        request_id="r1",
        user_id="u1",
        created_on=TODAY,
        title="Laptop",
        category="electronics",
        amount=money(amount),
        deadline=TODAY + timedelta(days=deadline_days),
        allows_partial=allows_partial,
        options=tuple(options),
    )
    return Case(profile, request, tuple(transactions), tuple(messages), tuple(fx_rates))
