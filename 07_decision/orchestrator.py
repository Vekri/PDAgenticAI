"""Local agent graph.

The desk runs one shared case through a fixed route. That is the orchestration
pattern from the architecture: specialists do the work, and one coordinator
owns the order. No paid agent framework is required.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.agents import (
    data_agent,
    decision_agent,
    financial_agent,
    knowledge_agent,
    orchestrate_agent,
    policy_agent,
    risk_agent,
    stamp,
)
from app.config import DB_PATH
from app.formatting import fmt_pct
from app.platform.release import release_manifest
from app.schemas import DecisionResult, LoanApplication
from app.store import save_decision


class Graph:
    def __init__(self) -> None:
        self.nodes = {}
        self.edges = {}
        self.entry: str | None = None

    def add_node(self, name: str, fn) -> "Graph":
        self.nodes[name] = fn
        return self

    def add_edge(self, source: str, target: str) -> "Graph":
        self.edges[source] = target
        return self

    def set_entry(self, name: str) -> "Graph":
        self.entry = name
        return self

    def path(self) -> list[str]:
        order = []
        current = self.entry
        seen = set()
        while current:
            if current in seen:
                raise RuntimeError("The agent graph contains a cycle.")
            seen.add(current)
            order.append(current)
            current = self.edges.get(current)
        return order

    def invoke(self, state: dict) -> dict:
        for name in self.path():
            state = self.nodes[name](state)
        state["path"] = self.path()
        return state


def build_graph() -> Graph:
    return (
        Graph()
        .add_node("data", data_agent)
        .add_node("knowledge", knowledge_agent)
        .add_node("financial", financial_agent)
        .add_node("risk", risk_agent)
        .add_node("policy", policy_agent)
        .add_node("orchestrate", orchestrate_agent)
        .add_node("decision", decision_agent)
        .set_entry("data")
        .add_edge("data", "knowledge")
        .add_edge("knowledge", "financial")
        .add_edge("financial", "risk")
        .add_edge("risk", "policy")
        .add_edge("policy", "orchestrate")
        .add_edge("orchestrate", "decision")
    )


def _package(state: dict, started: float) -> DecisionResult:
    app: LoanApplication = state["application"]
    metrics = state.get("metrics") or {}
    pd_block = state.get("pd") or {}
    pd_score = pd_block.get("pd")
    manifest = release_manifest()
    return DecisionResult(
        run_id=uuid.uuid4().hex[:12],
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        recommendation=state.get("recommendation") or "REVIEW",
        pd_score=pd_score,
        pd_display=fmt_pct(pd_score) if pd_score is not None else "n/a",
        risk_grade=pd_block.get("grade"),
        key_ratios={
            "debt_to_ebitda": metrics.get("debt_to_ebitda"),
            "dscr": metrics.get("dscr"),
            "credit_score": app.credit_score,
        },
        why=state.get("why") or [],
        explanation=state.get("explanation") or "",
        explanation_source=state.get("explanation_source") or "local-template",
        metrics=metrics,
        drivers=pd_block.get("drivers") or [],
        policy_checks=state.get("checks") or [],
        policy_evidence=state.get("evidence") or [],
        agents=state.get("agents") or [],
        audit=state.get("audit") or [],
        ml_pd=pd_block.get("ml_pd"),
        ml_backend=pd_block.get("ml_backend") or "not run",
        warnings=state.get("data_warnings") or [],
        errors=state.get("data_errors") or [],
        application=app.model_dump(mode="json"),
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        path=state.get("path") or [],
        app_version=manifest["app_version"],
        pipeline_version=manifest["pipeline_version"],
        policy_version=manifest["policy_version"],
        scorecard_version=manifest["scorecard_version"],
        ml_model_version=manifest["ml_model_version"],
        rag_corpus_version=manifest["rag_corpus_version"],
    )


def run_decision(
    application: LoanApplication,
    use_llm: bool = False,
    persist: bool = True,
    db_path: Path | None = None,
) -> DecisionResult:
    started = time.perf_counter()
    state = {
        "application": application,
        "use_llm": use_llm,
        "data_errors": [],
        "data_warnings": [],
        "metrics": None,
        "pd": None,
        "checks": [],
        "evidence": [],
        "recommendation": None,
        "why": [],
        "explanation": "",
        "explanation_source": "",
        "agents": [],
        "audit": [],
        "path": [],
    }
    stamp(
        state,
        1,
        "Receive Application",
        "Receive",
        "ok",
        f"Received {application.business_name} for {application.loan_purpose}.",
    )
    state = build_graph().invoke(state)
    result = _package(state, started)
    if persist:
        save_decision(result, db_path or DB_PATH)
    return result
