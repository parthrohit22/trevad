from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .engine import decide
from .errors import TrevadError
from .loader import case_from_dict, load_portfolio
from .serialize import decision_to_dict
from .validation import ensure_valid

WEB_DIR = Path(__file__).resolve().parent / "web"


def create_app(data_path: Path) -> FastAPI:
    portfolio = load_portfolio(Path(data_path))
    decided = {}
    for case in portfolio.cases:
        decision = decide(case)
        ensure_valid(case, decision)
        decided[case.request.request_id] = (case, decision)

    app = FastAPI(
        title="Trevad",
        version=__version__,
        description="Explainable affordability decisions from a 90-day cash forecast.",
    )

    @app.get("/api/v1/health")
    def health() -> Dict[str, Any]:
        return {"status": "ok", "requests": len(decided)}

    @app.get("/api/v1/requests")
    def list_requests():
        return [decision_to_dict(decision, case, detail=False) for case, decision in decided.values()]

    @app.get("/api/v1/requests/{request_id}")
    def get_request(request_id: str):
        if request_id not in decided:
            raise HTTPException(status_code=404, detail=f"No request {request_id}")
        case, decision = decided[request_id]
        return decision_to_dict(decision, case)

    @app.post("/api/v1/decisions")
    def create_decision(payload: Dict[str, Any] = Body(...)):
        try:
            case = case_from_dict(payload)
            decision = decide(case)
            ensure_valid(case, decision)
        except TrevadError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return decision_to_dict(decision, case)

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB_DIR / "index.html")

    return app
