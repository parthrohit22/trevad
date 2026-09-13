# API

Start the server:

```bash
python -m trevad serve --data data/demo_portfolio.json --port 8000
```

Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

## Endpoints

| Method | Path | Returns |
| --- | --- | --- |
| `GET` | `/api/v1/health` | `{"status": "ok", "requests": <count>}` |
| `GET` | `/api/v1/requests` | A summary decision for every request in the loaded portfolio |
| `GET` | `/api/v1/requests/{request_id}` | The full decision for one request; `404` if unknown |
| `POST` | `/api/v1/decisions` | The full decision for a case in the request body; `422` on invalid input |
| `GET` | `/` | The web interface |

Decisions for the loaded portfolio are computed and validated once at start-up.

## Decision

```json
{
  "request_id": "req-003",
  "user_id": "user-003",
  "currency": "GBP",
  "requested_amount": "1640.00",
  "minimum_balance": "711.00",
  "safe_to_pay_today": "450.79",
  "verdict": "affordable_with_plan",
  "method": "partial_payment",
  "schedule": [
    { "date": "2026-03-10", "amount": "450.79" },
    { "date": "2026-05-25", "amount": "1189.21" }
  ],
  "option_id": null,
  "earliest_full_payment_date": "2026-05-25",
  "spending_changes": [],
  "explanation": "Pay GBP 450.79 today and GBP 1,189.21 on 25 May 2026. Both payments keep your balance above the GBP 711 minimum.",
  "request": {
    "title": "Car service",
    "category": "transport",
    "created_on": "2026-03-10",
    "deadline": "2026-05-29",
    "allows_partial": true,
    "user_name": "Leo Martins",
    "balance": "2734.55",
    "accepted_methods": ["full_payment", "partial_payment"]
  }
}
```

The full decision adds:

| Field | Content |
| --- | --- |
| `forecast` | 91 daily points with the balance without the purchase (`baseline`) and with the recommendation (`with_plan`) |
| `candidates` | Every plan considered: payments, total, lowest balance, whether it was safe, and the rejection reason |
| `evidence` | Facts read from messages, including ignored instructions and unconfirmed claims |
| `cash_flows` | Every future cash flow used, with its source: `scheduled`, `projected`, or `evidence` |

`spending_changes` entries have `action` (`stop` or `reduce`),
`transaction_id`, `label`, `current_amount`, and `new_amount`.

All amounts are strings with two decimals, rounded down.
