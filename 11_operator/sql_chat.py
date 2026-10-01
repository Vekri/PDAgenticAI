"""Show a PostgreSQL read query and the rows it returns.

Plain questions map to the credit tables. A typed statement runs only when it
is a single SELECT against those tables.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

from app.platform.postgres import connect

QUERIES = (
    ("loan application", "SELECT * FROM credit.loan_application ORDER BY application_id"),
    ("financial", "SELECT * FROM credit.financial_statement ORDER BY application_id"),
    ("bureau", "SELECT * FROM credit.credit_bureau ORDER BY application_id"),
    ("credit score", "SELECT * FROM credit.credit_bureau ORDER BY application_id"),
    ("bank", "SELECT * FROM credit.bank_relationship ORDER BY application_id"),
    ("market", "SELECT * FROM credit.market_observation ORDER BY application_id"),
    ("joined file", """SELECT *
FROM credit.loan_application AS a
JOIN credit.financial_statement AS f USING (application_id)
JOIN credit.credit_bureau AS b USING (application_id)
JOIN credit.bank_relationship AS r USING (application_id)
JOIN credit.market_observation AS m USING (application_id)
ORDER BY a.application_id"""),
    ("full file", """SELECT *
FROM credit.loan_application AS a
JOIN credit.financial_statement AS f USING (application_id)
JOIN credit.credit_bureau AS b USING (application_id)
JOIN credit.bank_relationship AS r USING (application_id)
JOIN credit.market_observation AS m USING (application_id)
ORDER BY a.application_id"""),
    ("latest", "SELECT * FROM credit.latest_decision ORDER BY application_id"),
    ("feature", "SELECT * FROM credit.feature_record ORDER BY built_at"),
    ("check", "SELECT * FROM credit.decision_check ORDER BY run_id, check_order"),
    ("evidence", "SELECT * FROM credit.decision_evidence ORDER BY run_id, evidence_order"),
    ("audit", "SELECT * FROM credit.decision_audit ORDER BY run_id, step"),
    ("decision", "SELECT * FROM credit.decision ORDER BY created_at"),
    ("deployment", "SELECT * FROM credit.deployment ORDER BY deployed_at"),
    ("migration", "SELECT * FROM credit.schema_migration ORDER BY applied_at"),
    ("input load", "SELECT * FROM credit.input_load ORDER BY load_id"),
    ("schedule", "SELECT * FROM credit.schedule_capture ORDER BY capture_id"),
    ("pickup", "SELECT * FROM credit.schedule_capture ORDER BY capture_id"),
    ("operator", "SELECT * FROM credit.operator_log ORDER BY turn_id"),
)

ALLOWED_RELATIONS = {
    "credit.loan_application",
    "credit.financial_statement",
    "credit.credit_bureau",
    "credit.bank_relationship",
    "credit.market_observation",
    "credit.feature_record",
    "credit.decision",
    "credit.decision_check",
    "credit.decision_evidence",
    "credit.decision_audit",
    "credit.latest_decision",
    "credit.deployment",
    "credit.schema_migration",
    "credit.input_load",
    "credit.schedule_capture",
    "credit.operator_log",
}

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|execute|call|do|into|set|reset|comment|lock|notify|copy)\b",
    re.IGNORECASE,
)


_APPLICATION_TABLES = {
    "credit.loan_application",
    "credit.financial_statement",
    "credit.credit_bureau",
    "credit.bank_relationship",
    "credit.market_observation",
    "credit.feature_record",
    "credit.decision",
    "credit.latest_decision",
    "credit.input_load",
    "credit.schedule_capture",
}

_RUN_TABLES = {
    "credit.decision_check",
    "credit.decision_evidence",
    "credit.decision_audit",
}


def narrow_to_application(sql: str, application_id: str | None) -> tuple[str, str]:
    """Keep one loan file when the rows can be tied to an application id."""
    application = (application_id or "").strip()
    if not application:
        return sql, ""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", application):
        raise ValueError("Use a simple loan file id, such as apex.")
    relations = {item.lower() for item in re.findall(r"\bcredit\.[a-z_]+\b", sql, flags=re.IGNORECASE)}
    if relations and relations <= _APPLICATION_TABLES:
        return (
            f"SELECT * FROM ({sql}) AS scoped_rows WHERE application_id = '{application}'",
            "",
        )
    if relations and relations <= _RUN_TABLES:
        return (
            "SELECT * FROM ("
            + sql
            + ") AS scoped_rows WHERE run_id IN "
            + f"(SELECT run_id FROM credit.decision WHERE application_id = '{application}')",
            "",
        )
    return sql, "This table has no loan file id, so every row is shown."


def sql_for_question(message: str) -> str:
    text = " ".join(message.strip().split())
    if not text:
        raise ValueError("Type a table name or a SELECT.")
    lowered = text.lower().rstrip(";")
    if lowered.startswith("select") or lowered.startswith("with"):
        return guard_select(text)
    folded = lowered
    for phrase, sql in QUERIES:
        if phrase in folded:
            return sql
    known = ", ".join(sorted({item.split()[-1] for item in ALLOWED_RELATIONS}))
    raise ValueError(f"Name a credit table or paste one SELECT. Tables: {known}")


def guard_select(sql: str) -> str:
    text = sql.strip().rstrip(";").strip()
    if ";" in text or "--" in text or "/*" in text:
        raise ValueError("Use one SELECT with no comments.")
    if not re.match(r"(?is)^(select|with)\b", text):
        raise ValueError("Only a SELECT can be shown.")
    if _FORBIDDEN.search(text):
        raise ValueError("Only a read query can be shown.")
    relations = {item.lower() for item in re.findall(r"\bcredit\.[a-z_]+\b", text, flags=re.IGNORECASE)}
    if not relations or not relations <= ALLOWED_RELATIONS:
        raise ValueError("The query must read only the credit tables.")
    return text


def _plain(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def run_query(message: str, limit: int = 100, application_id: str | None = None) -> dict:
    sql, note = narrow_to_application(sql_for_question(message), application_id)
    wrapped = f"SELECT * FROM ({sql}) AS query_rows LIMIT {int(limit)}"
    with connect() as connection:
        rows = list(connection.execute(wrapped).fetchall())
    plain = [{key: _plain(value) for key, value in row.items()} for row in rows]
    columns = list(plain[0].keys()) if plain else []
    return {"sql": sql, "columns": columns, "rows": plain, "row_count": len(plain), "note": note}
