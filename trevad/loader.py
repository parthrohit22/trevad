from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

from .errors import DataError
from .models import (
    PAYMENT_METHODS,
    Case,
    FxRate,
    InstallmentOption,
    Message,
    Profile,
    PurchaseRequest,
    Transaction,
)

DIRECTIONS = {"in", "out"}
STATUSES = {"settled", "pending", "scheduled", "failed", "cancelled", "unrealized"}
KINDS = {"regular", "one_time", "refund", "transfer", "investment"}
FLEXIBILITY = {"fixed", "reducible", "stoppable", "reducible_or_stoppable"}


def _text(data: Mapping[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if value is None or not str(value).strip():
        raise DataError(f"{where}: '{key}' is required")
    return str(value).strip()


def _amount(data: Mapping[str, Any], key: str, where: str) -> Decimal:
    value = data.get(key)
    if value is None or isinstance(value, bool):
        raise DataError(f"{where}: '{key}' is required")
    try:
        return Decimal(str(value))
    except InvalidOperation as error:
        raise DataError(f"{where}: '{key}' must be a number") from error


def _optional_amount(data: Mapping[str, Any], key: str, where: str):
    return None if data.get(key) is None else _amount(data, key, where)


def _day(data: Mapping[str, Any], key: str, where: str) -> date:
    try:
        return date.fromisoformat(_text(data, key, where))
    except ValueError as error:
        raise DataError(f"{where}: '{key}' must be a YYYY-MM-DD date") from error


def _choice(data: Mapping[str, Any], key: str, where: str, allowed, default=None) -> str:
    value = data.get(key, default)
    if value not in allowed:
        raise DataError(f"{where}: '{key}' must be one of {', '.join(sorted(allowed))}")
    return value


def _names(data: Mapping[str, Any], key: str) -> frozenset:
    return frozenset(str(item) for item in (data.get(key) or []))


def profile_from_dict(data: Mapping[str, Any], where: str = "profile") -> Profile:
    methods = _names(data, "accepted_methods") or frozenset({"full_payment"})
    unknown = methods - set(PAYMENT_METHODS)
    if unknown:
        raise DataError(f"{where}: unknown payment methods {', '.join(sorted(unknown))}")
    limit = data.get("max_installments")
    return Profile(
        user_id=_text(data, "user_id", where),
        name=str(data.get("name") or data.get("user_id")),
        currency=_text(data, "currency", where).upper(),
        balance=_amount(data, "balance", where),
        minimum_balance=_amount(data, "minimum_balance", where),
        protected_categories=_names(data, "protected_categories"),
        reducible_categories=_names(data, "reducible_categories"),
        stoppable_categories=_names(data, "stoppable_categories"),
        accepted_methods=methods,
        max_installments=int(limit) if limit is not None else None,
    )


def transaction_from_dict(data: Mapping[str, Any], user_id: str, where: str) -> Transaction:
    return Transaction(
        transaction_id=_text(data, "id", where),
        user_id=user_id,
        description=_text(data, "description", where),
        category=_text(data, "category", where),
        direction=_choice(data, "direction", where, DIRECTIONS),
        amount=_amount(data, "amount", where),
        currency=_text(data, "currency", where).upper(),
        date=_day(data, "date", where),
        status=_choice(data, "status", where, STATUSES, "settled"),
        kind=_choice(data, "kind", where, KINDS, "one_time"),
        flexibility=_choice(data, "flexibility", where, FLEXIBILITY, "fixed"),
        minimum_amount=_optional_amount(data, "minimum_amount", where),
    )


def message_from_dict(data: Mapping[str, Any], user_id: str, where: str) -> Message:
    return Message(
        message_id=_text(data, "id", where),
        user_id=user_id,
        sent_on=_day(data, "sent_on", where),
        source=str(data.get("source") or "unknown"),
        text=_text(data, "text", where),
        transaction_id=data.get("transaction_id") or None,
    )


def fx_from_dict(data: Mapping[str, Any], where: str) -> FxRate:
    return FxRate(
        on=_day(data, "date", where),
        base=_text(data, "base", where).upper(),
        quote=_text(data, "quote", where).upper(),
        rate=_amount(data, "rate", where),
    )


def option_from_dict(data: Mapping[str, Any], where: str) -> InstallmentOption:
    return InstallmentOption(
        option_id=_text(data, "id", where),
        installment_amount=_amount(data, "installment_amount", where),
        count=int(_amount(data, "count", where)),
        first_date=_day(data, "first_date", where),
        interval_days=int(_amount(data, "interval_days", where)),
        fee=_optional_amount(data, "fee", where) or Decimal("0"),
        total=_amount(data, "total", where),
    )


def request_from_dict(data: Mapping[str, Any], user_id: str, where: str) -> PurchaseRequest:
    options = tuple(
        option_from_dict(item, f"{where}.installment_options[{index}]")
        for index, item in enumerate(data.get("installment_options") or [])
    )
    created = _day(data, "created_on", where)
    deadline = _day(data, "deadline", where)
    if deadline < created:
        raise DataError(f"{where}: deadline is before created_on")
    return PurchaseRequest(
        request_id=_text(data, "id", where),
        user_id=user_id,
        created_on=created,
        title=_text(data, "title", where),
        category=str(data.get("category") or "other"),
        amount=_amount(data, "amount", where),
        deadline=deadline,
        allows_partial=bool(data.get("allows_partial", False)),
        options=options,
    )


@dataclass(frozen=True)
class Portfolio:
    cases: Tuple[Case, ...]

    def find(self, request_id: str) -> Case:
        for case in self.cases:
            if case.request.request_id == request_id:
                return case
        raise KeyError(request_id)


def portfolio_from_dict(data: Mapping[str, Any]) -> Portfolio:
    fx_rates = tuple(fx_from_dict(item, f"fx_rates[{index}]") for index, item in enumerate(data.get("fx_rates") or []))
    cases: List[Case] = []
    seen: Dict[str, str] = {}
    for user_index, user in enumerate(data.get("users") or []):
        where = f"users[{user_index}]"
        profile = profile_from_dict(user.get("profile") or {}, f"{where}.profile")
        transactions = tuple(
            transaction_from_dict(item, profile.user_id, f"{where}.transactions[{index}]")
            for index, item in enumerate(user.get("transactions") or [])
        )
        messages = tuple(
            message_from_dict(item, profile.user_id, f"{where}.messages[{index}]")
            for index, item in enumerate(user.get("messages") or [])
        )
        for request_index, item in enumerate(user.get("requests") or []):
            request = request_from_dict(item, profile.user_id, f"{where}.requests[{request_index}]")
            if request.request_id in seen:
                raise DataError(f"duplicate request id {request.request_id}")
            seen[request.request_id] = profile.user_id
            cases.append(Case(profile, request, transactions, messages, fx_rates))
    return Portfolio(tuple(cases))


def load_portfolio(path: Path) -> Portfolio:
    if not path.is_file():
        raise DataError(f"data file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise DataError(f"{path} is not valid JSON: {error}") from error
    return portfolio_from_dict(data)


def case_from_dict(data: Mapping[str, Any]) -> Case:
    profile = profile_from_dict(data.get("profile") or {})
    transactions = tuple(
        transaction_from_dict(item, profile.user_id, f"transactions[{index}]")
        for index, item in enumerate(data.get("transactions") or [])
    )
    messages = tuple(
        message_from_dict(item, profile.user_id, f"messages[{index}]")
        for index, item in enumerate(data.get("messages") or [])
    )
    fx_rates = tuple(fx_from_dict(item, f"fx_rates[{index}]") for index, item in enumerate(data.get("fx_rates") or []))
    request = request_from_dict(data.get("request") or {}, profile.user_id, "request")
    return Case(profile, request, transactions, messages, fx_rates)
