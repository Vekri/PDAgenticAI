"""Local operator. Talk to the credit system and run its existing steps.

The model may choose a tool. The tool runs the real code. The reply is built
from that result, and the turn is stored in credit.operator_log.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal

from app.config import INBOX, database_url
from app.data_engineering.warehouse import decide_stored, list_applications
from app.llm import groq_complete, groq_status
from app.platform.postgres import connect, postgres_status
from app.platform.release import release_manifest
from app.rag import get_index

TOOLS = ("monitor", "list", "score", "explain", "search", "load_inbox", "help")


def _plain(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _rows(rows: list[dict]) -> list[dict]:
    return [{key: _plain(value) for key, value in row.items()} for row in rows]


def monitor_snapshot() -> dict:
    inbox_files = sorted(path.name for path in INBOX.glob("*.json")) if INBOX.exists() else []
    snapshot = {
        "release": release_manifest(),
        "llm": groq_status(),
        "postgres": postgres_status(),
        "inbox_waiting": inbox_files,
        "latest": [],
        "pickups": [],
        "operator_turns": 0,
    }
    if not snapshot["postgres"].get("ok"):
        return snapshot
    with connect() as connection:
        snapshot["latest"] = _rows(
            list(
                connection.execute(
                    """
                    SELECT application_id, recommendation, pd_display, risk_grade, run_id
                    FROM credit.latest_decision
                    ORDER BY application_id
                    """
                ).fetchall()
            )
        )
        snapshot["pickups"] = _rows(
            list(
                connection.execute(
                    """
                    SELECT file_name, application_id, load_action, recommendation, pd_display, captured_at
                    FROM credit.schedule_capture
                    ORDER BY capture_id DESC
                    LIMIT 8
                    """
                ).fetchall()
            )
        )
        try:
            snapshot["operator_turns"] = connection.execute("SELECT count(*) AS n FROM credit.operator_log").fetchone()["n"]
        except Exception:
            snapshot["operator_turns"] = 0
    return snapshot


def _known_ids(connection) -> list[str]:
    return [
        row["application_id"]
        for row in connection.execute("SELECT application_id FROM credit.loan_application ORDER BY application_id").fetchall()
    ]


def _require_id(application_id: str | None) -> str:
    if application_id:
        return application_id
    raise ValueError("Name the application id, for example apex.")


def run_tool(tool: str, application_id: str | None = None, query: str | None = None, use_llm: bool = False) -> dict:
    if tool == "help":
        return {
            "ok": True,
            "tool": tool,
            "text": (
                "I can monitor the system, list files, score an id, explain an id, "
                "search policy, or load new JSON from the desktop inbox."
            ),
        }
    if tool == "monitor":
        snapshot = monitor_snapshot()
        lines = [
            f"Release {snapshot['release']['app_version']} · {snapshot['release']['policy_version']}",
            f"Groq {'ready' if snapshot['llm'].get('ok') else 'key not set'}",
            f"PostgreSQL {'connected' if snapshot['postgres'].get('ok') else 'unavailable'}",
            f"Inbox files waiting: {len(snapshot['inbox_waiting'])}",
            f"Operator turns stored: {snapshot['operator_turns']}",
        ]
        for row in snapshot["latest"]:
            lines.append(f"{row['application_id']}: {row['recommendation']} {row['pd_display']} {row['risk_grade']}")
        return {"ok": True, "tool": tool, "text": "\n".join(lines), "snapshot": snapshot}
    if tool == "search":
        hits = get_index().search(query or "credit policy approval", k=3)
        if not hits:
            return {"ok": True, "tool": tool, "text": "No policy section matched."}
        lines = [f"{hit['source']} {hit['section']} {hit['title']}" for hit in hits]
        return {"ok": True, "tool": tool, "text": "\n".join(lines)}
    if not database_url():
        return {"ok": False, "tool": tool, "text": "Set DATABASE_URL before I can read or score the warehouse."}
    if tool == "list":
        with connect() as connection:
            rows = _rows(list_applications(connection))
        if not rows:
            return {"ok": True, "tool": tool, "text": "No loan files are loaded."}
        lines = [
            f"{row['application_id']}: {row['business_name']} · {row.get('recommendation') or 'not scored'} {row.get('pd_display') or ''}".rstrip()
            for row in rows
        ]
        return {"ok": True, "tool": tool, "text": "\n".join(lines)}
    if tool == "score":
        application_id = _require_id(application_id)
        result = decide_stored(application_id, use_llm=use_llm)
        ratios = result.key_ratios or {}
        text = (
            f"{application_id}: {result.recommendation} PD {result.pd_display} grade {result.risk_grade}. "
            f"Debt/EBITDA {ratios.get('debt_to_ebitda')} DSCR {ratios.get('dscr')} "
            f"score {ratios.get('credit_score')}. Run {result.run_id}."
        )
        return {"ok": True, "tool": tool, "text": text, "run_id": result.run_id}
    if tool == "explain":
        application_id = _require_id(application_id)
        with connect() as connection:
            row = connection.execute(
                """
                SELECT recommendation, pd_display, risk_grade, why_json, explanation, run_id
                FROM credit.latest_decision d
                JOIN credit.decision USING (run_id)
                WHERE d.application_id = %s
                """,
                (application_id,),
            ).fetchone()
        if row is None:
            return {"ok": False, "tool": tool, "text": f"{application_id} has no stored decision yet. Ask me to score it."}
        why = row["why_json"] if isinstance(row["why_json"], list) else json.loads(row["why_json"])
        text = f"{application_id}: {row['recommendation']} {row['pd_display']} {row['risk_grade']}.\n" + "\n".join(why)
        return {"ok": True, "tool": tool, "text": text, "run_id": row["run_id"]}
    if tool == "load_inbox":
        from importlib.util import module_from_spec, spec_from_file_location

        from app.config import ROOT

        path = ROOT / "10_schedule_and_deploy" / "scheduled_incremental_load.py"
        spec = spec_from_file_location("scheduled_incremental_load", path)
        if spec is None or spec.loader is None:
            raise RuntimeError("The inbox loader is missing.")
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        module.main()
        waiting = sorted(item.name for item in INBOX.glob("*.json")) if INBOX.exists() else []
        text = "Inbox load finished."
        if waiting:
            text += " Still waiting: " + ", ".join(waiting)
        return {"ok": True, "tool": tool, "text": text}
    raise ValueError(f"Unknown tool '{tool}'.")


def _id_from_text(message: str) -> str | None:
    match = re.search(r"\b(apex|harbor|northwind|cedar|summit|ridge)\b", message, re.I)
    if match:
        return match.group(1).lower()
    quoted = re.search(r"\b(?:id|file|application)\s+([a-z][a-z0-9_-]{1,40})\b", message, re.I)
    if quoted:
        return quoted.group(1).lower()
    return None


def choose_tool(message: str) -> dict:
    text = message.lower()
    application_id = _id_from_text(message)
    if any(word in text for word in ("help", "what can you")):
        tool = "help"
    elif any(word in text for word in ("inbox", "pickup", "pick up", "new file", "load new")):
        tool = "load_inbox"
    elif any(word in text for word in ("monitor", "status", "health", "how is", "process")):
        tool = "monitor"
    elif any(word in text for word in ("list", "which file", "show files", "applications")):
        tool = "list"
    elif any(word in text for word in ("why", "explain", "reason")):
        tool = "explain"
    elif any(word in text for word in ("policy", "section", "search")):
        tool = "search"
    elif any(word in text for word in ("score", "decide", "run ")):
        tool = "score"
    else:
        tool = _choose_with_llm(message) or "help"
    query = message if tool == "search" else None
    return {"tool": tool, "application_id": application_id, "query": query, "use_llm": "memo" in text}


def _choose_with_llm(message: str) -> str | None:
    prompt = (
        "Choose one tool for the user message. Reply with only the tool name.\n"
        f"Tools: {', '.join(TOOLS)}\n"
        f"Message: {message}"
    )
    answer = groq_complete(prompt, max_tokens=40)
    if not answer:
        return None
    answer = answer.lower()
    for name in TOOLS:
        if name in answer:
            return name
    return None


def _log(message: str, tool: str, ok: bool, reply: str, source: str) -> None:
    if not database_url():
        return
    try:
        from app.platform.postgres import migrate

        migrate()
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO credit.operator_log (message, tool_name, tool_ok, reply, source)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (message, tool, ok, reply[:4000], source),
            )
            connection.commit()
    except Exception:
        return


def ask(message: str) -> dict:
    choice = choose_tool(message)
    source = "rules"
    try:
        result = run_tool(
            choice["tool"],
            application_id=choice.get("application_id"),
            query=choice.get("query"),
            use_llm=bool(choice.get("use_llm")),
        )
    except Exception as exc:
        result = {"ok": False, "tool": choice["tool"], "text": str(exc)}
    reply = result["text"]
    spoken = _speak(message, reply)
    if spoken:
        reply = spoken + "\n\n" + result["text"]
        source = "groq"
    _log(message, result["tool"], bool(result.get("ok")), reply, source)
    return {"reply": reply, "tool": result["tool"], "ok": bool(result.get("ok")), "source": source, "snapshot": result.get("snapshot")}


def _speak(message: str, facts: str) -> str | None:
    prompt = (
        "You are the credit system operator. Answer the user in two or three sentences. "
        "Use only these facts. Do not invent a decision, a PD, or a file.\n\n"
        f"User: {message}\nFacts:\n{facts}"
    )
    text = groq_complete(prompt, max_tokens=220)
    return text[:1200] if text else None
