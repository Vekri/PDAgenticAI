"""Specialist agents. Each one reads and updates the shared case state."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from app.financials import calculate_metrics
from app.formatting import fmt_pct, fmt_ratio, money
from app.llm import write_explanation
from app.pd_model import INDUSTRIES, OUTLOOKS, score_application
from app.policy_rules import evaluate, recommendation_from, why_lines
from app.rag import get_index


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def stamp(state: dict, step: int, name: str, short: str, status: str, detail: str) -> None:
    state["audit"].append(
        {
            "step": step,
            "name": name,
            "short": short,
            "status": status,
            "detail": detail,
            "at": _now(),
        }
    )


def record_agent(state: dict, name: str, role: str, status: str, summary: str, details: dict, started: float) -> None:
    state["agents"].append(
        {
            "name": name,
            "role": role,
            "status": status,
            "summary": summary,
            "details": details,
            "duration_ms": _ms(started),
        }
    )


def data_agent(state: dict) -> dict:
    started = time.perf_counter()
    app = state["application"].model_copy(deep=True)
    errors: list[str] = []
    warnings: list[str] = []
    app.business_name = app.business_name.strip()
    app.loan_purpose = app.loan_purpose.strip()

    if not app.business_name:
        errors.append("Business name is required.")
    if app.ebitda <= 0:
        errors.append("EBITDA must be positive before the file can be scored.")
    if app.revenue <= 0:
        errors.append("Revenue must be positive.")
    if app.current_liabilities <= 0:
        errors.append("Current liabilities must be greater than zero to compute liquidity ratios.")
    if not 300 <= app.credit_score <= 850:
        errors.append("Credit score must be between 300 and 850.")
    if app.interest_expense < 0:
        errors.append("Interest expense cannot be negative.")
    if app.industry not in INDUSTRIES:
        errors.append("Industry is not on the approved industry list.")
    if app.equity <= 0:
        errors.append("Equity must be positive before leverage ratios can be scored.")
    if app.industry_outlook not in OUTLOOKS:
        warnings.append("Industry outlook was not recognized and was treated as Stable for the scorecard.")
        app.industry_outlook = "Stable"
    if app.net_income < 0:
        warnings.append("Net income is negative.")
    if app.interest_rate_pct < 4 or app.interest_rate_pct > 18:
        warnings.append("Interest rate is outside the 4% to 18% desk range. The payment was still calculated from the rate entered.")
    if app.total_assets + 1 < app.existing_debt + app.equity:
        warnings.append("Total assets are less than existing debt plus equity. Check the balance sheet.")
    if not app.loan_purpose:
        warnings.append("Loan purpose is empty.")
    if app.revenue > 0 and app.loan_amount > 0.5 * app.revenue:
        warnings.append("Proposed loan exceeds 50% of revenue.")
    if app.relationship_years == 0 and app.deposit_balance <= 0:
        warnings.append("No deposit relationship is on file.")

    state["application"] = app
    state["data_errors"] = errors
    state["data_warnings"] = warnings
    if errors:
        status = "fail"
        summary = "The file is incomplete, so it cannot be straight-through scored. " + " ".join(errors)
    elif warnings:
        status = "warn"
        summary = "Application data is usable. " + " ".join(warnings)
    else:
        status = "ok"
        summary = "Application, statements, bureau, internal, and market fields passed validation."
    record_agent(
        state,
        "Data Agent",
        "Validate application data",
        status,
        summary,
        {"errors": errors, "warnings": warnings},
        started,
    )
    stamp(state, 2, "Validate & Clean Data", "Validate", status, summary)
    return state


def knowledge_agent(state: dict) -> dict:
    started = time.perf_counter()
    app = state["application"]
    index = get_index()
    query = (
        f"{app.industry} {app.loan_purpose} business loan straight-through approval "
        "decline DSCR debt EBITDA probability of default credit score"
    )
    evidence: list[dict] = []
    for section in ("§4.2", "§3.1"):
        hit = index.get(section)
        if hit:
            evidence.append(
                {
                    "source": hit["source"],
                    "section": hit["section"],
                    "title": hit["title"],
                    "excerpt": hit["excerpt"],
                    "score": None,
                    "origin": "Cited section",
                }
            )
    for hit in index.search(query, k=4):
        if any(item["section"] == hit["section"] and item["source"] == hit["source"] for item in evidence):
            continue
        evidence.append(
            {
                "source": hit["source"],
                "section": hit["section"],
                "title": hit["title"],
                "excerpt": hit["excerpt"],
                "score": hit.get("score"),
                "origin": "Retrieved passage",
            }
        )
    state["evidence"] = evidence
    summary = (
        f"Retrieved {len(evidence)} policy passages from the local corpus, "
        "including Credit Policy §4.2 and Risk Policy §3.1."
    )
    record_agent(
        state,
        "Knowledge Agent",
        "Ground the file in internal policy",
        "ok",
        summary,
        {"query": query, "passages": len(evidence)},
        started,
    )
    stamp(state, 3, "Retrieve Policies (RAG)", "Policies", "ok", summary)
    return state


def financial_agent(state: dict) -> dict:
    started = time.perf_counter()
    metrics = calculate_metrics(state["application"])
    state["metrics"] = metrics
    if state["data_errors"] or metrics.get("debt_to_ebitda") is None or metrics.get("dscr") is None:
        status = "warn"
        summary = "Ratios that depend on missing or non-positive figures were left blank."
    else:
        status = "ok"
        summary = (
            f"Pro forma debt is {money(metrics['pro_forma_debt'])}. "
            f"Debt/EBITDA is {fmt_ratio(metrics['debt_to_ebitda'])}. "
            f"DSCR is {fmt_ratio(metrics['dscr'])}, using EBITDA over existing debt service "
            f"plus a new annual payment of {money(metrics['proposed_annual_payment'])}."
        )
    record_agent(
        state,
        "Financial Agent",
        "Calculate ratios and metrics",
        status,
        summary,
        metrics,
        started,
    )
    stamp(state, 4, "Calculate Financial Metrics", "Metrics", status, summary)
    return state


def risk_agent(state: dict) -> dict:
    started = time.perf_counter()
    scored = None if state["data_errors"] else score_application(state["application"], state["metrics"])
    state["pd"] = scored
    if scored is None:
        status = "warn"
        summary = "The PD model was not run because the file could not be scored."
        details: dict = {}
    else:
        status = "ok"
        cross = fmt_pct(scored["ml_pd"]) if scored.get("ml_pd") is not None else "n/a"
        summary = (
            f"Policy scorecard PD is {fmt_pct(scored['pd'])} ({scored['grade']}). "
            f"The local {scored['ml_backend']} cross-check is {cross} and does not change the decision."
        )
        details = {
            "pd": scored["pd"],
            "grade": scored["grade"],
            "logit": scored["logit"],
            "ml_pd": scored["ml_pd"],
            "ml_backend": scored["ml_backend"],
            "drivers": scored["drivers"],
        }
    record_agent(state, "Risk Agent", "Run the PD model", status, summary, details, started)
    stamp(state, 5, "Run PD Model", "PD model", status, summary)
    return state


def policy_agent(state: dict) -> dict:
    started = time.perf_counter()
    pd_value = None if not state.get("pd") else state["pd"]["pd"]
    checks = evaluate(state["application"], state["metrics"] or {}, pd_value, state["data_errors"])
    recommendation = recommendation_from(checks)
    why = why_lines(recommendation, checks)
    state["checks"] = [item.model_dump() for item in checks]
    state["recommendation"] = recommendation
    state["why"] = why
    failed = [item for item in checks if not item.passed and item.level in {"hard", "preferred", "data"}]
    if recommendation == "APPROVE":
        status = "ok"
        summary = "Every straight-through condition passed. No hard stop was triggered."
    elif recommendation == "REJECT":
        status = "fail"
        summary = f"{len(failed)} policy test(s) failed, including a hard stop."
    else:
        status = "warn"
        summary = f"{len(failed)} policy test(s) need a credit officer. No hard stop was triggered." if not any(
            not item.passed and item.level == "hard" for item in checks
        ) else f"{len(failed)} policy test(s) failed."
    record_agent(
        state,
        "Policy Agent",
        "Check policy compliance",
        status,
        summary,
        {"recommendation": recommendation, "failed": len(failed), "checks": len(checks)},
        started,
    )
    stamp(state, 6, "Check Policy Rules", "Policy", status, summary)
    return state


def orchestrate_agent(state: dict) -> dict:
    started = time.perf_counter()
    route = "Data Agent → Knowledge (RAG) → Financial Agent → Risk Agent → Policy Agent → Decision Agent"
    summary = f"Orchestrator passed one shared case file along {route}."
    record_agent(
        state,
        "Orchestrator Agent",
        "Coordinate the specialist agents",
        "ok",
        summary,
        {"route": route},
        started,
    )
    stamp(state, 7, "Multi-Agent Orchestration", "Orchestrate", "ok", summary)
    return state


def decision_agent(state: dict) -> dict:
    started = time.perf_counter()
    app = state["application"]
    pd_block = state.get("pd") or {}
    pd_display = fmt_pct(pd_block.get("pd")) if pd_block else "n/a"
    grade = pd_block.get("grade") if pd_block else None
    text, source = write_explanation(
        app,
        state["recommendation"],
        pd_display,
        grade,
        state.get("metrics") or {},
        state["why"],
        state.get("evidence") or [],
        state["use_llm"],
    )
    state["explanation"] = text
    state["explanation_source"] = source
    status = {"APPROVE": "ok", "REVIEW": "warn", "REJECT": "fail"}.get(state["recommendation"], "info")
    summary = f"Recommendation is {state['recommendation']}. Explanation source: {source}."
    record_agent(
        state,
        "Decision Agent",
        "Generate recommendation and explanation",
        status,
        summary,
        {"explanation_source": source, "why": state["why"]},
        started,
    )
    stamp(state, 8, "Final Decision & Explanation", "Decision", status, summary)
    return state
