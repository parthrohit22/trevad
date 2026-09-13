# Data Format

Trevad reads JSON. A portfolio file holds many users, each with their own
history, messages, and requests. The API accepts a single case with the same
building blocks.

All amounts are numbers or numeric strings. All dates are `YYYY-MM-DD`.
Amounts on a profile and a request are in the user's `currency`; each
transaction carries its own currency.

## Portfolio file

```json
{
  "fx_rates": [
    { "date": "2026-03-01", "base": "EUR", "quote": "USD", "rate": "1.09" }
  ],
  "users": [
    {
      "profile": { },
      "transactions": [ ],
      "messages": [ ],
      "requests": [ ]
    }
  ]
}
```

## Profile

| Field | Required | Meaning |
| --- | --- | --- |
| `user_id` | yes | Unique user ID |
| `name` | no | Display name |
| `currency` | yes | Home currency, for example `USD` |
| `balance` | yes | Available balance today |
| `minimum_balance` | yes | Balance the user never wants to go below |
| `protected_categories` | no | Categories that are never changed |
| `reducible_categories` | no | Categories the user is willing to reduce |
| `stoppable_categories` | no | Categories the user is willing to stop |
| `accepted_methods` | no | Any of `full_payment`, `partial_payment`, `installments`; defaults to `full_payment` |
| `max_installments` | no | Largest number of installment payments the user accepts |

## Transaction

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Unique transaction ID |
| `description` | yes | Text as it appears on the statement |
| `category` | yes | For example `rent`, `groceries`, `salary` |
| `direction` | yes | `in` or `out` |
| `amount` | yes | Positive amount |
| `currency` | yes | Currency of the amount |
| `date` | yes | Settlement date, or expected date for pending and scheduled records |
| `status` | no | `settled` (default), `pending`, `scheduled`, `failed`, `cancelled`, `unrealized` |
| `kind` | no | `one_time` (default), `regular`, `refund`, `transfer`, `investment` |
| `flexibility` | no | `fixed` (default), `reducible`, `stoppable`, `reducible_or_stoppable` |
| `minimum_amount` | no | Lowest amount a reducible expense can go to |

## Message

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Unique message ID |
| `sent_on` | yes | Date the message was received |
| `text` | yes | Message body |
| `source` | no | For example `employer`, `landlord`, `merchant` |
| `transaction_id` | no | Set when the message is about one specific transaction |

## Request

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Unique request ID |
| `created_on` | yes | Date the decision is made for |
| `title` | yes | What the money is for |
| `category` | no | For example `electronics`, `travel` |
| `amount` | yes | Price in the user's currency |
| `deadline` | yes | Last date the payment can be completed |
| `allows_partial` | no | Whether the seller accepts part now and the rest later |
| `installment_options` | no | Installment plans offered by the seller |

## Installment option

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Unique option ID |
| `installment_amount` | yes | Amount of each payment |
| `count` | yes | Number of payments |
| `first_date` | yes | Date of the first payment |
| `interval_days` | yes | Days between payments |
| `fee` | no | Financing fee included in the total |
| `total` | yes | Total paid over the plan |

## Single case (API)

`POST /api/v1/decisions` takes one case:

```json
{
  "profile": {
    "user_id": "u-1",
    "currency": "USD",
    "balance": 3000,
    "minimum_balance": 1000,
    "accepted_methods": ["full_payment", "partial_payment"]
  },
  "transactions": [
    { "id": "t-1", "description": "Payroll", "category": "salary", "direction": "in",
      "amount": 3000, "currency": "USD", "date": "2026-02-25", "kind": "regular" }
  ],
  "messages": [],
  "fx_rates": [],
  "request": {
    "id": "r-1", "created_on": "2026-03-10", "title": "Laptop",
    "amount": 1500, "deadline": "2026-05-09", "allows_partial": true
  }
}
```

Invalid input returns HTTP 422 with a message naming the field, for example
`request: 'created_on' must be a YYYY-MM-DD date`.
