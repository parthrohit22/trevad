from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

Direction = Literal["in", "out"]
Status = Literal["settled", "pending", "scheduled", "failed", "cancelled", "unrealized"]
Flexibility = Literal["fixed", "reducible", "stoppable", "reducible_or_stoppable"]
TransactionKind = Literal["regular", "one_time", "refund", "transfer", "investment"]
Method = Literal["full_payment", "partial_payment", "installments", "wait", "not_recommended"]
Verdict = Literal["affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"]
FlowSource = Literal["projected", "scheduled", "evidence"]
ChangeAction = Literal["stop", "reduce"]

PAYMENT_METHODS: tuple[str, ...] = ("full_payment", "partial_payment", "installments")


@dataclass(frozen=True)
class Profile:
    user_id: str
    name: str
    currency: str
    balance: Decimal
    minimum_balance: Decimal
    protected_categories: frozenset[str] = frozenset()
    reducible_categories: frozenset[str] = frozenset()
    stoppable_categories: frozenset[str] = frozenset()
    accepted_methods: frozenset[str] = frozenset({"full_payment"})
    max_installments: int | None = None


@dataclass(frozen=True)
class Transaction:
    transaction_id: str
    user_id: str
    description: str
    category: str
    direction: Direction
    amount: Decimal
    currency: str
    date: date
    status: Status = "settled"
    kind: TransactionKind = "one_time"
    flexibility: Flexibility = "fixed"
    minimum_amount: Decimal | None = None


@dataclass(frozen=True)
class Message:
    message_id: str
    user_id: str
    sent_on: date
    source: str
    text: str
    transaction_id: str | None = None


@dataclass(frozen=True)
class FxRate:
    on: date
    base: str
    quote: str
    rate: Decimal


@dataclass(frozen=True)
class InstallmentOption:
    option_id: str
    installment_amount: Decimal
    count: int
    first_date: date
    interval_days: int
    fee: Decimal
    total: Decimal


@dataclass(frozen=True)
class PurchaseRequest:
    request_id: str
    user_id: str
    created_on: date
    title: str
    category: str
    amount: Decimal
    deadline: date
    allows_partial: bool = False
    options: tuple[InstallmentOption, ...] = ()


@dataclass(frozen=True)
class Case:
    profile: Profile
    request: PurchaseRequest
    transactions: tuple[Transaction, ...] = ()
    messages: tuple[Message, ...] = ()
    fx_rates: tuple[FxRate, ...] = ()


@dataclass(frozen=True)
class Series:
    series_id: str
    label: str
    category: str
    direction: Direction
    currency: str
    amount: Decimal
    monthly: bool
    interval_days: int | None
    last_date: date
    last_transaction_id: str
    flexibility: Flexibility
    minimum_amount: Decimal | None


@dataclass(frozen=True)
class Flow:
    on: date
    amount: Decimal
    direction: Direction
    category: str
    label: str
    source: FlowSource
    reference: str
    series_id: str | None = None

    @property
    def signed(self) -> Decimal:
        return self.amount if self.direction == "in" else -self.amount


@dataclass(frozen=True)
class Fact:
    kind: str
    message_id: str
    summary: str
    transaction_id: str | None = None
    category: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    on: date | None = None
    percent: Decimal | None = None


@dataclass(frozen=True)
class Payment:
    on: date
    amount: Decimal


@dataclass(frozen=True)
class SpendingChange:
    action: ChangeAction
    series_id: str
    transaction_id: str
    label: str
    currency: str
    current_amount: Decimal
    new_amount: Decimal


@dataclass
class Candidate:
    method: Method
    payments: tuple[Payment, ...]
    total: Decimal
    option_id: str | None = None
    changes: tuple[SpendingChange, ...] = ()
    safe: bool = False
    lowest_balance: Decimal | None = None
    lowest_on: date | None = None
    rejection: str | None = None


@dataclass(frozen=True)
class Capacity:
    safe_today: Decimal
    earliest_full: date | None
    balances: tuple[tuple[date, Decimal], ...]


@dataclass(frozen=True)
class Decision:
    request_id: str
    user_id: str
    currency: str
    requested_amount: Decimal
    minimum_balance: Decimal
    safe_to_pay_today: Decimal
    verdict: Verdict
    method: Method
    schedule: tuple[Payment, ...]
    option_id: str | None
    earliest_full_payment_date: date | None
    spending_changes: tuple[SpendingChange, ...]
    explanation: str
    baseline_forecast: tuple[tuple[date, Decimal], ...]
    plan_forecast: tuple[tuple[date, Decimal], ...]
    candidates: tuple[Candidate, ...]
    facts: tuple[Fact, ...]
    flows: tuple[Flow, ...]
