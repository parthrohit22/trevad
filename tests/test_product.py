from __future__ import annotations

import csv
import json
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from conftest import TODAY
from trevad.api import create_app
from trevad.cli import main
from trevad.engine import decide
from trevad.errors import DataError
from trevad.loader import case_from_dict, portfolio_from_dict
from trevad.synthetic import generate_portfolio
from trevad.validation import ensure_valid


@pytest.fixture(scope="module")
def portfolio_data():
    return generate_portfolio(users=28, seed=7)


@pytest.fixture(scope="module")
def data_file(tmp_path_factory, portfolio_data):
    path = tmp_path_factory.mktemp("data") / "portfolio.json"
    path.write_text(json.dumps(portfolio_data), encoding="utf-8")
    return path


def test_generator_is_reproducible():
    assert generate_portfolio(users=6, seed=3) == generate_portfolio(users=6, seed=3)
    assert generate_portfolio(users=6, seed=3) != generate_portfolio(users=6, seed=4)


def test_every_generated_request_gets_a_valid_decision(portfolio_data):
    portfolio = portfolio_from_dict(portfolio_data)
    verdicts = Counter()
    methods = Counter()
    for case in portfolio.cases:
        decision = decide(case)
        ensure_valid(case, decision)
        verdicts[decision.verdict] += 1
        methods[decision.method] += 1
    assert set(verdicts) == {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}
    assert {"full_payment", "partial_payment", "installments", "wait", "not_recommended"} <= set(methods)


def test_loader_reports_clear_errors():
    with pytest.raises(DataError, match="'balance' is required"):
        portfolio_from_dict({"users": [{"profile": {"user_id": "u", "currency": "USD", "minimum_balance": 1}}]})
    with pytest.raises(DataError, match="YYYY-MM-DD"):
        case_from_dict({
            "profile": {"user_id": "u", "currency": "USD", "balance": 10, "minimum_balance": 1},
            "request": {"id": "r", "created_on": "10/03/2026", "title": "x", "amount": 5, "deadline": "2026-04-01"},
        })
    with pytest.raises(DataError, match="unknown payment methods"):
        case_from_dict({
            "profile": {"user_id": "u", "currency": "USD", "balance": 10, "minimum_balance": 1, "accepted_methods": ["crypto"]},
            "request": {"id": "r", "created_on": "2026-03-10", "title": "x", "amount": 5, "deadline": "2026-04-01"},
        })


def test_cli_generate_and_decide(tmp_path):
    data = tmp_path / "portfolio.json"
    assert main(["generate", "--users", "14", "--seed", "11", "--output", str(data)]) == 0
    out_csv, out_json = tmp_path / "decisions.csv", tmp_path / "decisions.json"
    assert main(["decide", str(data), "--csv", str(out_csv), "--json", str(out_json)]) == 0
    rows = list(csv.DictReader(out_csv.open(encoding="utf-8")))
    requests = sum(len(user["requests"]) for user in json.loads(data.read_text())["users"])
    assert len(rows) == requests
    assert len(json.loads(out_json.read_text())) == requests


def test_cli_reports_missing_file(tmp_path, capsys):
    assert main(["decide", str(tmp_path / "missing.json")]) == 2
    assert "data file not found" in capsys.readouterr().err


def test_api_lists_and_explains_decisions(data_file):
    client = TestClient(create_app(data_file))
    health = client.get("/api/v1/health").json()
    assert health["status"] == "ok" and health["requests"] > 0

    listing = client.get("/api/v1/requests").json()
    assert len(listing) == health["requests"]
    first = listing[0]["request_id"]

    detail = client.get(f"/api/v1/requests/{first}").json()
    assert len(detail["forecast"]) == 91
    assert {"candidates", "evidence", "cash_flows", "schedule", "explanation"} <= set(detail)
    assert client.get("/api/v1/requests/does-not-exist").status_code == 404


def test_api_decides_a_posted_case(data_file):
    client = TestClient(create_app(data_file))
    payload = {
        "profile": {"user_id": "api-user", "currency": "USD", "balance": 4000, "minimum_balance": 1000, "accepted_methods": ["full_payment"]},
        "transactions": [],
        "request": {"id": "api-1", "created_on": TODAY.isoformat(), "title": "Bike", "amount": 500, "deadline": "2026-04-30"},
    }
    response = client.post("/api/v1/decisions", json=payload)
    assert response.status_code == 200
    assert response.json()["verdict"] == "affordable_now"

    payload["request"]["deadline"] = "2026-01-01"
    assert client.post("/api/v1/decisions", json=payload).status_code == 422


def test_web_interface_is_served(data_file):
    client = TestClient(create_app(data_file))
    page = client.get("/")
    assert page.status_code == 200 and "Trevad" in page.text
    assert client.get("/static/app.js").status_code == 200
