"""Local explanation writer.

Ollama is used when it is running on this PC. The policy recommendation is
already decided before this module is called. If no local model is available,
a grounded template states the same facts.
"""

from __future__ import annotations

import json
import urllib.request

from app.config import OLLAMA_HOST, groq_api_key
from app.formatting import fmt_pct, fmt_ratio, money

PREFERRED_MODELS = ("llama3.2", "llama3.1", "llama3", "mistral", "phi3", "gemma2", "qwen2.5", "llama3.2:latest")


def ollama_status(timeout: float = 1.2) -> dict:
    host = OLLAMA_HOST.rstrip("/")
    try:
        request = urllib.request.Request(host + "/api/tags")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        models = [item.get("name", "") for item in body.get("models", []) if item.get("name")]
        return {"ok": True, "models": models, "host": host}
    except Exception as exc:
        return {"ok": False, "models": [], "host": host, "error": str(exc)}


def choose_model(models: list[str]) -> str | None:
    if not models:
        return None
    by_base = {name.split(":")[0]: name for name in models}
    for preferred in PREFERRED_MODELS:
        base = preferred.split(":")[0]
        if preferred in models:
            return preferred
        if base in by_base:
            return by_base[base]
    return models[0]


def template_explanation(app, recommendation: str, pd_display: str, grade: str | None, metrics: dict, why: list[str]) -> str:
    grade_bit = f" ({grade})" if grade else ""
    dte = fmt_ratio(metrics.get("debt_to_ebitda")) if metrics else "n/a"
    dscr = fmt_ratio(metrics.get("dscr")) if metrics else "n/a"
    relationship = (
        f"The internal relationship is {app.relationship_years} years with deposits of {money(app.deposit_balance)}. "
        f"Prior loans are {'current' if app.prior_loans_current else 'not current'}."
    )
    reasons = " ".join(why)
    paragraphs = [
        (
            f"{app.business_name} requested {money(app.loan_amount)} for {app.loan_purpose.lower()} "
            f"over {app.loan_term_years} years at {app.interest_rate_pct:.1f} percent. "
            f"The officer asked: \"{app.analyst_request.strip()}\""
        ),
        (
            f"Recommendation: {recommendation}. The policy scorecard probability of default is {pd_display}{grade_bit}. "
            f"Pro forma Debt/EBITDA is {dte} and DSCR is {dscr}. "
            f"The commercial credit score is {app.credit_score}. {reasons}"
        ),
        (
            f"{relationship} Industry is {app.industry} and the outlook on file is {app.industry_outlook}. "
            "Figures come from the application, bureau, internal, and market inputs. "
            "This is decision support: a credit officer owns the final call, and each agent step is in the local audit trail."
        ),
    ]
    return "\n\n".join(paragraphs)


def _prompt(app, recommendation: str, pd_display: str, grade: str | None, metrics: dict, why: list[str], evidence: list[dict]) -> str:
    excerpts = []
    for item in evidence[:4]:
        excerpts.append(f"{item['source']} {item['section']}: {item['excerpt'][:280]}")
    facts = {
        "business": app.business_name,
        "recommendation": recommendation,
        "pd": pd_display,
        "grade": grade,
        "debt_to_ebitda": fmt_ratio(metrics.get("debt_to_ebitda")) if metrics else None,
        "dscr": fmt_ratio(metrics.get("dscr")) if metrics else None,
        "credit_score": app.credit_score,
        "loan_amount": money(app.loan_amount),
        "purpose": app.loan_purpose,
        "why": why,
    }
    return (
        "You are a credit officer's writing assistant. Write two short paragraphs. "
        "Use only the facts below. Do not change the recommendation. Do not invent numbers. "
        "Do not mention that you are an AI.\n\n"
        f"Officer request: {app.analyst_request.strip()}\n"
        f"Facts: {json.dumps(facts)}\n"
        f"Policy excerpts:\n" + "\n".join(excerpts)
    )


def draft_with_llm(app, recommendation: str, pd_display: str, grade: str | None, metrics: dict, why: list[str], evidence: list[dict]) -> tuple[str | None, str]:
    status = ollama_status()
    if not status["ok"]:
        return None, "local-template"
    model = choose_model(status["models"])
    if not model:
        return None, "local-template"
    payload = json.dumps(
        {
            "model": model,
            "prompt": _prompt(app, recommendation, pd_display, grade, metrics, why, evidence),
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 320},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        status["host"] + "/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = (body.get("response") or "").strip()
        if not text:
            return None, "local-template"
        return text[:2000], f"ollama:{model}"
    except Exception:
        return None, "local-template"


def draft_with_groq(app, recommendation: str, pd_display: str, grade: str | None, metrics: dict, why: list[str], evidence: list[dict]) -> tuple[str | None, str]:
    key = groq_api_key()
    if not key:
        return None, "local-template"
    payload = json.dumps(
        {
            "model": "openai/gpt-oss-20b",
            "temperature": 0.2,
            "max_tokens": 800,
            "messages": [
                {
                    "role": "user",
                    "content": _prompt(app, recommendation, pd_display, grade, metrics, why, evidence),
                }
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "pdagentic-desk/1.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = (body["choices"][0]["message"]["content"] or "").strip()
        if not text:
            return None, "local-template"
        return text[:2000], "groq:openai/gpt-oss-20b"
    except Exception:
        return None, "local-template"


def write_explanation(app, recommendation: str, pd_display: str, grade: str | None, metrics: dict, why: list[str], evidence: list[dict], use_llm: bool) -> tuple[str, str]:
    text = None
    source = "local-template"
    if use_llm:
        text, source = draft_with_llm(app, recommendation, pd_display, grade, metrics, why, evidence)
    if not text and groq_api_key():
        text, source = draft_with_groq(app, recommendation, pd_display, grade, metrics, why, evidence)
    if not text:
        text = template_explanation(app, recommendation, pd_display, grade, metrics, why)
        source = "local-template"
    if recommendation not in text.upper():
        text = f"Recommendation: {recommendation}.\n\n{text}"
    return text, source
