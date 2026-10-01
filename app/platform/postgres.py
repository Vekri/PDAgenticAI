"""PostgreSQL connection, migrations, and the current deployment row."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.config import MIGRATIONS_DIR, database_url
from app.platform.release import deployment_id, release_manifest

_READY = False
_DEPLOYMENT_ID = ""


class PlatformError(RuntimeError):
    pass


def _statements(script: str) -> list[str]:
    return [part.strip() for part in script.split(";") if part.strip()]


def _redact(detail: str) -> str:
    return re.sub(r"://[^/\s]+@", "://", detail)


def _candidate_urls(url: str) -> list[str]:
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    if not any(key == "channel_binding" for key, _ in query):
        return [url]
    stripped = [(key, value) for key, value in query if key != "channel_binding"]
    fallback = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(stripped), parts.fragment))
    return [url, fallback]


def postgres_configured() -> bool:
    return bool(database_url())


def connect():
    url = database_url()
    if not url:
        raise PlatformError(
            "DATABASE_URL is not set. In the Streamlit app menu, open Settings, Secrets, "
            "save DATABASE_URL, then reboot."
        )
    from psycopg.rows import dict_row
    import psycopg

    last_error: Exception | None = None
    for candidate in _candidate_urls(url):
        try:
            return psycopg.connect(candidate, row_factory=dict_row)
        except Exception as exc:
            last_error = exc
            message = str(exc).lower()
            if "channel binding" not in message and "channel_binding" not in message:
                raise
    if last_error is not None:
        raise last_error
    raise PlatformError("Could not connect to PostgreSQL.")


def migrate() -> list[str]:
    applied: list[str] = []
    with connect() as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS credit")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS credit.schema_migration (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        connection.commit()
        done = {
            row["version"]
            for row in connection.execute("SELECT version FROM credit.schema_migration").fetchall()
        }
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done:
                continue
            for statement in _statements(path.read_text(encoding="utf-8")):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO credit.schema_migration (version) VALUES (%s)",
                (path.name,),
            )
            connection.commit()
            applied.append(path.name)
    return applied


def register_deployment() -> str:
    global _DEPLOYMENT_ID
    manifest = release_manifest()
    identifier = deployment_id(manifest)
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO credit.deployment (
                deployment_id, environment, app_version, pipeline_version,
                policy_version, scorecard_version, ml_model_version, rag_corpus_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (deployment_id) DO NOTHING
            """,
            (
                identifier,
                manifest["environment"],
                manifest["app_version"],
                manifest["pipeline_version"],
                manifest["policy_version"],
                manifest["scorecard_version"],
                manifest["ml_model_version"],
                manifest["rag_corpus_version"],
            ),
        )
        connection.commit()
    _DEPLOYMENT_ID = identifier
    return identifier


def current_deployment_id() -> str:
    if not _DEPLOYMENT_ID:
        raise PlatformError("The platform deployment has not been registered.")
    return _DEPLOYMENT_ID


def ensure_platform() -> str:
    global _READY
    if _READY and _DEPLOYMENT_ID:
        return _DEPLOYMENT_ID
    from app.data_engineering.warehouse import seed_missing_samples

    migrate()
    identifier = register_deployment()
    seed_missing_samples()
    _READY = True
    return identifier


def postgres_status() -> dict:
    if not postgres_configured():
        return {
            "ok": False,
            "detail": (
                "DATABASE_URL is not set. In the Streamlit app menu, open Settings, "
                "Secrets, save DATABASE_URL, then reboot."
            ),
        }
    try:
        ensure_platform()
        with connect() as connection:
            applications = connection.execute("SELECT count(*) AS n FROM credit.loan_application").fetchone()["n"]
            decisions = connection.execute("SELECT count(*) AS n FROM credit.decision").fetchone()["n"]
        return {
            "ok": True,
            "deployment_id": current_deployment_id(),
            "applications": applications,
            "decisions": decisions,
            **release_manifest(),
        }
    except Exception as exc:
        return {"ok": False, "detail": _redact(str(exc))}
