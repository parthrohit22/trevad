from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import List, Optional

from .engine import decide
from .errors import TrevadError
from .loader import load_portfolio
from .serialize import decision_to_dict, write_csv, write_json
from .synthetic import DEFAULT_TODAY, generate_portfolio
from .validation import ensure_valid

DEFAULT_DATA = Path("data/demo_portfolio.json")
VERDICT_ORDER = ("affordable_now", "affordable_with_plan", "affordable_later", "not_affordable")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trevad", description="Explainable affordability decisions from a 90-day cash forecast.")
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate", help="create a synthetic demo portfolio")
    generate.add_argument("--users", type=int, default=28)
    generate.add_argument("--seed", type=int, default=7)
    generate.add_argument("--today", type=date.fromisoformat, default=DEFAULT_TODAY)
    generate.add_argument("--output", type=Path, default=DEFAULT_DATA)

    run = commands.add_parser("decide", help="decide every request in a portfolio")
    run.add_argument("data", type=Path, nargs="?", default=DEFAULT_DATA)
    run.add_argument("--csv", type=Path, default=Path("out/decisions.csv"))
    run.add_argument("--json", type=Path, default=Path("out/decisions.json"))

    show = commands.add_parser("explain", help="show the full decision for one request")
    show.add_argument("request_id")
    show.add_argument("--data", type=Path, default=DEFAULT_DATA)

    serve = commands.add_parser("serve", help="start the API and web interface")
    serve.add_argument("--data", type=Path, default=DEFAULT_DATA)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def cmd_generate(args) -> int:
    portfolio = generate_portfolio(users=args.users, seed=args.seed, today=args.today)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(portfolio, indent=2) + "\n", encoding="utf-8")
    requests = sum(len(user["requests"]) for user in portfolio["users"])
    print(f"Generated {args.users} users and {requests} requests in {args.output}")
    return 0


def cmd_decide(args) -> int:
    portfolio = load_portfolio(args.data)
    decisions = []
    for case in portfolio.cases:
        decision = decide(case)
        ensure_valid(case, decision)
        decisions.append(decision)
    write_csv(args.csv, decisions)
    write_json(args.json, decisions, portfolio.cases)
    counts = Counter(decision.verdict for decision in decisions)
    print(f"Decided {len(decisions)} requests, all passed validation.")
    for verdict in VERDICT_ORDER:
        print(f"  {verdict:<22} {counts.get(verdict, 0)}")
    print(f"Wrote {args.csv} and {args.json}")
    return 0


def cmd_explain(args) -> int:
    portfolio = load_portfolio(args.data)
    try:
        case = portfolio.find(args.request_id)
    except KeyError:
        print(f"error: no request {args.request_id}", file=sys.stderr)
        return 2
    decision = decide(case)
    ensure_valid(case, decision)
    data = decision_to_dict(decision, case)
    print(f"{case.request.title} for {case.profile.name} ({data['currency']} {data['requested_amount']})")
    print(f"Verdict:        {data['verdict']}")
    print(f"Method:         {data['method']}")
    print(f"Safe today:     {data['currency']} {data['safe_to_pay_today']}")
    print(f"Earliest full:  {data['earliest_full_payment_date'] or 'not within 90 days'}")
    for payment in data["schedule"]:
        print(f"Pay:            {payment['date']}  {data['currency']} {payment['amount']}")
    for change in data["spending_changes"]:
        print(f"Change:         {change['action']} {change['label']} -> {change['new_amount']}")
    for fact in data["evidence"]:
        print(f"Evidence:       {fact['summary']} ({fact['message_id']})")
    print(f"Explanation:    {data['explanation']}")
    print("Plans considered:")
    for candidate in data["candidates"]:
        label = candidate["method"] + (f" {candidate['option_id']}" if candidate["option_id"] else "")
        if candidate["changes"]:
            label += " + " + ", ".join(f"{change['action']} {change['label']}" for change in candidate["changes"])
        outcome = "safe" if candidate["safe"] else candidate["rejection"]
        print(f"  - {label}: {outcome}")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from .api import create_app

    uvicorn.run(create_app(args.data), host=args.host, port=args.port)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"generate": cmd_generate, "decide": cmd_decide, "explain": cmd_explain, "serve": cmd_serve}
    try:
        return handlers[args.command](args)
    except TrevadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
