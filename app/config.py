"""Paths and local runtime settings."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = ROOT / "04_rag_policy" / "knowledge"
DATA_DIR = ROOT / "data"
DB_PATH = Path(os.environ.get("PD_DB_PATH", DATA_DIR / "decisions.db"))
MIGRATIONS_DIR = ROOT / "01_database" / "migrations"
INBOX = ROOT / "data" / "inbox"


def load_runtime_secrets() -> None:
    """Copy a Streamlit secrets file into the process environment."""
    try:
        from streamlit.runtime.secrets import secrets_singleton

        secrets_singleton.load_if_toml_exists()
    except Exception:
        return


def database_url() -> str:
    load_runtime_secrets()
    return os.environ.get("DATABASE_URL", "").strip()


def groq_api_key() -> str:
    load_runtime_secrets()
    return os.environ.get("GROQ_API_KEY", "").strip()


load_runtime_secrets()
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
PD_ENV = os.environ.get("PD_ENV", "local").strip() or "local"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").strip()
