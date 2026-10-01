"""Local HTTP API for the same decision pipeline the desk uses."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import __version__
from app.config import DATABASE_URL
from app.data_engineering.warehouse import decide_stored, fetch_decision, land_and_decide, list_applications
from app.llm import ollama_status
from app.operator import ask, monitor_snapshot
from app.orchestrator import run_decision
from app.pd_model import get_ml_model
from app.platform.postgres import connect, postgres_status
from app.platform.release import release_manifest
from app.rag import get_index
from app.samples import SAMPLE_CATALOG, get_sample
from app.schemas import DecisionResult, LoanApplication
from app.store import ensure_db, get_decision, list_decisions

@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_db()
    get_index()
    get_ml_model()
    if DATABASE_URL:
        postgres_status()
    yield


app = FastAPI(
    title="Agentic AI for Business Loan Decisioning",
    version=__version__,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_postgres() -> None:
    status = postgres_status()
    if not status.get("ok"):
        raise HTTPException(status_code=503, detail=status.get("detail") or "PostgreSQL is unavailable.")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "release": release_manifest(),
        "llm": ollama_status(),
        "rag_chunks": len(get_index()),
        "saved_decisions": len(list_decisions(500)),
        "postgres": postgres_status(),
    }


@app.get("/release")
def release() -> dict:
    return release_manifest()


@app.get("/samples")
def samples() -> dict:
    return {
        "samples": [
            {**item, "application": get_sample(item["id"]).model_dump(mode="json")}
            for item in SAMPLE_CATALOG
        ]
    }


@app.post("/decide", response_model=DecisionResult)
def decide(application: LoanApplication, use_llm: bool = False) -> DecisionResult:
    return run_decision(application, use_llm=use_llm, persist=True)


@app.post("/decide/sample/{sample_name}", response_model=DecisionResult)
def decide_sample(sample_name: str, use_llm: bool = False) -> DecisionResult:
    try:
        application = get_sample(sample_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return run_decision(application, use_llm=use_llm, persist=True)


@app.get("/decisions")
def decisions(limit: int = 20) -> dict:
    return {"decisions": list_decisions(limit)}


@app.get("/decisions/{run_id}")
def decision(run_id: str) -> dict:
    payload = get_decision(run_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="No saved decision with that id.")
    return payload


@app.get("/warehouse/applications")
def warehouse_applications() -> dict:
    _require_postgres()
    with connect() as connection:
        rows = list_applications(connection)
    return {"applications": rows}


@app.post("/warehouse/applications/{application_id}", response_model=DecisionResult)
def warehouse_land(application_id: str, application: LoanApplication, use_llm: bool = False) -> DecisionResult:
    _require_postgres()
    return land_and_decide(application_id, application, use_llm=use_llm)


@app.post("/warehouse/applications/{application_id}/decide", response_model=DecisionResult)
def warehouse_decide(application_id: str, use_llm: bool = False) -> DecisionResult:
    _require_postgres()
    try:
        return decide_stored(application_id, use_llm=use_llm)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/warehouse/decisions/{run_id}")
def warehouse_decision(run_id: str) -> dict:
    _require_postgres()
    with connect() as connection:
        payload = fetch_decision(connection, run_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="No warehouse decision with that id.")
    return payload


class OperatorMessage(BaseModel):
    message: str


@app.get("/operator/monitor")
def operator_monitor() -> dict:
    return monitor_snapshot()


@app.post("/operator/chat")
def operator_chat(body: OperatorMessage) -> dict:
    return ask(body.message)


@app.get("/policies/search")
def search_policies(q: str) -> dict:
    hits = []
    for hit in get_index().search(q, k=4):
        hits.append({key: value for key, value in hit.items() if key != "text"})
    return {"query": q, "hits": hits}
