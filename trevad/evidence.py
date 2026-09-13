from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Iterable, Mapping

from .models import Fact, Message, Transaction
from .money import display, to_decimal

CURRENCY = r"(?:USD|EUR|GBP|INR|ZAR|IDR|AUD|CAD|SGD|JPY|CHF|NZD|AED)"
AMOUNT = r"\d[\d,]*(?:\.\d+)?"
MONEY_RE = re.compile(rf"(?P<c1>{CURRENCY})\s?(?P<a1>{AMOUNT})|(?P<a2>{AMOUNT})\s?(?P<c2>{CURRENCY})")
DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s?%")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

INCOME_WORD = r"(?:salary|pay ?check|payroll|wages|pay ?day|net pay)"

INSTRUCTION_RE = re.compile(
    r"(?i)\b(ignore (?:all|any|the|previous|prior)\b|disregard (?:the|all|previous)\b"
    r"|mark (?:this|it|me|the request) as\b|you must (?:approve|recommend)\b"
    r"|system prompt|override (?:the )?rules?)"
)
CANCEL_RE = re.compile(r"(?i)\b(cancel+ed|called off|voided|will not be charged|no longer due)\b")
OUTSTANDING_RE = re.compile(
    r"(?i)\b(still (?:due|outstanding|unpaid|owed)|remains (?:due|unpaid|outstanding)|will be retried)\b"
)
MOVED_RE = re.compile(r"(?i)\b(moved|rescheduled|postponed|delayed|pushed back|brought forward)\b")
AMEND_RE = re.compile(r"(?i)\b(corrected|amended|updated|revised|adjusted)\b")
UNCERTAIN_RE = re.compile(
    r"(?i)\b(may|might|could|hope|hoping|expect(?:ed)? to|possibly|not yet confirmed"
    r"|pending approval|if approved)\b"
)
INCOME_RE = re.compile(rf"(?i)\b{INCOME_WORD}\b")
INCOME_ENDED_RE = re.compile(
    r"(?i)\b(?:contract|employment|job|position|role)\b[^.]*\b(?:ended|ends|terminated|finished|will end)\b"
    rf"|\b(?:final|last) {INCOME_WORD}\b"
)
INCOME_MOVED_RE = re.compile(
    r"(?i)\b(moved|rescheduled|postponed|delayed|pushed back|now (?:expected|arriving|paid)"
    r"|will (?:arrive|be paid))\b"
)
CHANGE_RE = re.compile(
    r"(?i)\b(increase[sd]?|raised?|rise[sn]?|goes up|reduced|decrease[sd]?|cut|changes?|will be|is now|new)\b"
)
RISE_RE = re.compile(r"(?i)\b(increase[sd]?|rise[sn]?|goes up|go up|raised?)\b")
ONE_TIME_RE = re.compile(
    r"(?i)\b(invoice|reimbursement|settlement|payout|transfer)\b[^.]*"
    r"\b(approved|confirmed|cleared|scheduled|will be paid|will arrive)\b"
)
EXPENSE_CATEGORIES = (
    "rent", "mortgage", "insurance", "utilities", "internet", "phone", "childcare",
    "tuition", "subscription", "gym", "transport", "loan",
)


def _money(text: str) -> tuple[str, Decimal] | None:
    match = MONEY_RE.search(text)
    if not match:
        return None
    currency = match["c1"] or match["c2"]
    return currency, to_decimal(match["a1"] or match["a2"])


def _date(text: str) -> date | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def _linked_facts(message: Message, sentence: str, linked: Transaction) -> list[Fact]:
    identifier = message.message_id
    when = _date(sentence)
    money = _money(sentence)
    name = linked.description
    if CANCEL_RE.search(sentence):
        return [Fact("transaction_cancelled", identifier, f"{name} was cancelled", linked.transaction_id)]
    if OUTSTANDING_RE.search(sentence) and linked.status == "failed":
        return [Fact("bill_outstanding", identifier, f"{name} is still outstanding", linked.transaction_id, on=when)]
    if MOVED_RE.search(sentence) and when:
        return [Fact("transaction_moved", identifier, f"{name} moved to {when.isoformat()}", linked.transaction_id, on=when)]
    if AMEND_RE.search(sentence) and money:
        currency, amount = money
        return [
            Fact(
                "transaction_amended", identifier, f"{name} corrected to {display(amount, currency)}",
                linked.transaction_id, amount=amount, currency=currency,
            )
        ]
    return []


def _open_facts(message: Message, sentence: str) -> list[Fact]:
    identifier = message.message_id
    when = _date(sentence)
    money = _money(sentence)
    uncertain = bool(UNCERTAIN_RE.search(sentence))

    if INCOME_ENDED_RE.search(sentence):
        suffix = f" from {when.isoformat()}" if when else ""
        return [Fact("income_ended", identifier, f"Regular income ends{suffix}", on=when)]

    if INCOME_RE.search(sentence):
        if uncertain:
            return [Fact("unconfirmed", identifier, "Unconfirmed income change, not used")]
        if money and CHANGE_RE.search(sentence):
            currency, amount = money
            suffix = f" from {when.isoformat()}" if when else ""
            return [
                Fact(
                    "income_changed", identifier, f"Regular income becomes {display(amount, currency)}{suffix}",
                    amount=amount, currency=currency, on=when,
                )
            ]
        if when and INCOME_MOVED_RE.search(sentence):
            return [Fact("income_moved", identifier, f"Next salary arrives on {when.isoformat()}", on=when)]
        return []

    percent = PERCENT_RE.search(sentence)
    if percent and RISE_RE.search(sentence):
        lower = sentence.lower()
        for category in EXPENSE_CATEGORIES:
            if re.search(rf"\b{category}\b", lower):
                value = to_decimal(percent.group(1))
                suffix = f" from {when.isoformat()}" if when else ""
                return [
                    Fact(
                        "expense_changed", identifier, f"{category.title()} rises by {value}%{suffix}",
                        category=category, percent=value, on=when,
                    )
                ]

    if ONE_TIME_RE.search(sentence) and money and when:
        if uncertain:
            return [Fact("unconfirmed", identifier, "Unconfirmed one-time income, not used")]
        currency, amount = money
        return [
            Fact(
                "one_time_income", identifier,
                f"{display(amount, currency)} confirmed for {when.isoformat()}",
                amount=amount, currency=currency, on=when,
            )
        ]
    return []


def extract_facts(
    messages: Iterable[Message],
    transactions: Mapping[str, Transaction],
    as_of: date,
) -> list[Fact]:
    facts: list[Fact] = []
    for message in sorted(messages, key=lambda item: (item.sent_on, item.message_id)):
        if message.sent_on > as_of:
            continue
        if INSTRUCTION_RE.search(message.text):
            facts.append(
                Fact(
                    "ignored_instruction", message.message_id,
                    "Contains instructions aimed at the system; treated as data only",
                )
            )
        linked = transactions.get(message.transaction_id) if message.transaction_id else None
        for sentence in SENTENCE_RE.split(message.text):
            if INSTRUCTION_RE.search(sentence):
                continue
            if linked is not None:
                facts.extend(_linked_facts(message, sentence, linked))
            else:
                facts.extend(_open_facts(message, sentence))
    return facts
