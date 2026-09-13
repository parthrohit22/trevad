# ADR 0001: Replay Every Plan Against a Daily Forecast

**Status:** Accepted

## Context

"Can I afford this?" depends on timing as much as on the balance. Rent can land
before salary, a delayed payroll can open a gap, and an installment plan can
look cheap but hit the account on a bad day. A recommendation is only useful
if every payment in it can actually be made without dropping below the
minimum the user chose.

## Decision

- Turn all evidence (history, pending records, messages, exchange rates) into
  one list of dated cash flows.
- Simulate the balance for each of the next 90 days.
- Generate every plan the user would accept and replay each one through that
  simulation. Only plans that never breach the minimum can be selected.
- Rank safe plans with fixed rules, and check the result with a validator that
  does not reuse the planner.
- Keep message reading rule-based and limit it to changing cash flows.

## Consequences

Positive:

- Every recommendation comes with a proof: the lowest balance and its date.
- Rejected plans come with a concrete reason, which the interface shows.
- The same input always gives the same output, with no runtime model cost.

Trade-offs:

- Message patterns have to be written and maintained by hand.
- The forecast is only as good as the recurring patterns in the history.
- Explanations are templated rather than conversational.

## Alternatives considered

- **Compare the price with today's balance:** ignores bills and income that
  arrive before the payment clears.
- **Ask a language model for the decision:** cannot guarantee the schedule is
  solvent and gives different answers to the same question.
- **Monthly budget totals instead of daily balances:** hides the exact days
  when the account runs lowest.
