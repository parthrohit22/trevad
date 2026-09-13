# Decision Policy

These are the rules the engine applies, in the order it applies them. Each
rule points to the module that implements it.

## 1. Clean the records (`forecast.py`)

- Records with the same direction, category, amount, currency, date, and
  description are duplicates. One is kept, preferring settled, then scheduled,
  then pending.
- Messages sent after the request date are ignored.

## 2. Read the messages (`evidence.py`)

Messages are split into sentences and matched against fixed patterns.

| Evidence | Effect on the forecast |
| --- | --- |
| Linked record is cancelled or will not be charged | Record removed |
| Linked failed bill is still outstanding or will be retried | Reserved again from the request date |
| Linked pending record moved to a new date | Record moved |
| Linked record corrected to a new amount | Amount replaced |
| Contract, job, or employment ended, or final payroll | Salary removed from that date (or from today) |
| Salary delayed or moved to a date | Next salary moved to that date |
| Salary changes to a stated amount | Future salary uses the new amount from its start date |
| Rent, insurance, utilities, and similar rise by a percentage | Future amounts increased from the stated date |
| Invoice, reimbursement, or payout confirmed with amount and date | One incoming payment on that date |
| Any of the above phrased as uncertain ("may", "if approved", "not yet confirmed") | Recorded as unconfirmed, not used |
| Text that tries to instruct the system ("ignore previous rules", "mark as approved") | Recorded as ignored, sentence skipped |

## 3. Find recurring money (`recurrence.py`)

Only settled records on or before the request date are used. Refunds,
transfers, and investment records never form a series. Income described as a
bonus, commission, reimbursement, refund, prize, gift, arrears, or tip is
treated as irregular.

A group of records with the same direction, category, currency, and
description becomes a series when it has at least three occurrences and:

- **monthly:** the last six dates fall within two days of the same day of the
  month, 26 to 35 days apart, or
- **weekly or fortnightly:** the most common gap is 7 or 14 days and appears
  in at least half the gaps.

| Series | Projected amount |
| --- | --- |
| Expense | Highest of the last three amounts |
| Income | Lowest of the last three amounts; rejected if the last five vary by more than 5%, or the latest is marked final |

A series that has not appeared for two full intervals is treated as ended.

## 4. Build future cash flows (`forecast.py`)

| Record | Counted |
| --- | --- |
| Pending or scheduled expense | Yes, on its date or today if already due |
| Scheduled income | Yes, on its date |
| Pending income | No, until it settles |
| Failed, cancelled, unrealized | No |
| Recurring series | Every occurrence inside the 90 days, unless a scheduled record for the same series falls within 7 days |

Foreign-currency amounts are converted with the latest rate on or before the
flow's date, directly or through the inverse pair. A missing rate stops the
decision with an error.

## 5. Measure capacity (`ledger.py`)

The balance is simulated for the request date and each of the next 90 days.
For every day the engine keeps the lowest balance from that day to the end.

```text
safe_to_pay_today           = min(amount, max(0, lowest_from_today - minimum_balance))
earliest_full_payment_date  = first day where lowest_from_that_day - minimum_balance >= amount
```

Both are measured before any spending change, and the safe amount is rounded
down to the cent.

## 6. Build candidate plans (`planner.py`)

| Plan | Built when | Rejected when |
| --- | --- | --- |
| Full payment today | The user accepts full payment | The replay breaches the minimum |
| Wait | The user accepts full payment and full payment becomes safe after today | That date is after the deadline |
| Partial payment | Partial payment is allowed and accepted, some but not all is safe today, and the rest becomes safe by the deadline | The replay breaches the minimum |
| Installments | The user accepts installments; one plan per supplied option, with its exact dates and amounts | More payments than the user's limit, pays less than the price, ends after the deadline, or starts before the request |

Every plan that is not rejected up front is replayed through the full
forecast. It is safe only if the lowest balance stays at or above the minimum.

## 7. Spending changes (`planner.py`)

Only when no plan is safe as it is. A recurring expense can be changed when it
is not in a protected category and:

- **stop:** its category is one the user will stop, and it is marked
  `stoppable` or `reducible_or_stoppable`
- **reduce:** its category is one the user will reduce, and it is marked
  `reducible` or `reducible_or_stoppable`; it is reduced to its stated minimum

The engine tries one change, then two, then three, on different expenses, and
stops at the smallest number that makes any plan safe.

## 8. Rank the safe plans (`planner.py`)

The lowest value wins, compared in this order:

1. Number of spending changes
2. Total amount cut from spending
3. Total paid, including fees
4. Date of the first payment
5. Number of payments
6. Option ID

## 9. Verdict (`engine.py`)

| Selected plan | Verdict |
| --- | --- |
| Full payment today, no changes | `affordable_now` |
| Wait | `affordable_later` |
| Partial, installments, or any plan with changes | `affordable_with_plan` |
| No safe plan | `not_affordable`, method `not_recommended` |

## 10. Validation (`validation.py`)

Every decision is checked before it is returned:

- `0 <= safe_to_pay_today <= amount`
- verdict and method are consistent
- payments are positive, in date order, not before the request, not after the
  deadline
- the method is one the user accepts
- full payment is the whole amount today; wait is one payment on the earliest
  safe date; partial is the safe amount today and the rest on the earliest
  safe date
- installments match a supplied option exactly, respect the user's limit, and
  pay at least the price
- at most three changes, on different expenses, none protected, each allowed
  by the user and by the expense's flexibility
- the earliest full payment date is inside the forecast
