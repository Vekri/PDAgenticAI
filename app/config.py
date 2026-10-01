"""Paths and local runtime settings."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = ROOT / "04_rag_policy" / "knowledge"
DATA_DIR = ROOT / "data"
DB_PATH = Path(os.environ.get("PD_DB_PATH", DATA_DIR / "decisions.db"))
MIGRATIONS_DIR = ROOT / "01_database" / "migrations"
DATABASE_URL = os.environ.get("DATABASE_URL", "")
PD_ENV = os.environ.get("PD_ENV", "local")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
