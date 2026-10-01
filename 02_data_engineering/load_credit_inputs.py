"""Create database credit on local PostgreSQL and load the input tables.

Step 1. Connect as user postgres, password postgre, port 5432.
Step 2. Create database credit when it is missing.
Step 3. Create schema credit and the five input tables.
Step 4. Load apex, harbor, and northwind.
Step 5. Upsert every file in 02_data_engineering/incremental. A second run updates the same ids.

Run from the project folder:

    .venv\\Scripts\\python scripts\\load_credit_inputs.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PG_HOST = "localhost"
PG_PORT = 5432
PG_USER = "postgres"
PG_PASSWORD = "postgre"
PG_DATABASE = "credit"
ADMIN_URL = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/postgres"
LOCAL_URL = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"
INCOMING_URL = os.environ.get("DATABASE_URL", "").strip()


def _cloud_database(url: str) -> bool:
    lowered = url.lower()
    return bool(url) and "localhost" not in lowered and "127.0.0.1" not in lowered


if _cloud_database(INCOMING_URL):
    os.environ["DATABASE_URL"] = INCOMING_URL
    os.environ["PD_ENV"] = os.environ.get("PD_ENV", "production")
else:
    os.environ["DATABASE_URL"] = LOCAL_URL
    os.environ["PD_ENV"] = "local"

import psycopg

from app.data_engineering.warehouse import upsert_sources
from app.platform.postgres import connect, migrate
from app.samples import SAMPLE_CATALOG, get_sample
from app.schemas import LoanApplication

INCREMENTAL_DIR = ROOT / "02_data_engineering" / "incremental"
INPUT_TABLES = (
    "loan_application",
    "financial_statement",
    "credit_bureau",
    "bank_relationship",
    "market_observation",
)


def step(number: int, message: str) -> None:
    print(f"\nStep {number}. {message}")


def create_database() -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (PG_DATABASE,),
        ).fetchone()
        if exists:
            print(f"Database {PG_DATABASE} already exists.")
            return
        connection.execute(f'CREATE DATABASE "{PG_DATABASE}"')
        print(f"Created database {PG_DATABASE}.")


def ensure_load_log(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS credit.input_load (
            load_id BIGSERIAL PRIMARY KEY,
            batch_name TEXT NOT NULL,
            application_id TEXT NOT NULL,
            action TEXT NOT NULL,
            loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def upsert_batch(connection, batch_name: str, rows: list[tuple[str, LoanApplication]]) -> None:
    for application_id, application in rows:
        found = connection.execute(
            "SELECT 1 FROM credit.loan_application WHERE application_id = %s",
            (application_id,),
        ).fetchone()
        upsert_sources(connection, application_id, application)
        action = "updated" if found else "inserted"
        connection.execute(
            """
            INSERT INTO credit.input_load (batch_name, application_id, action)
            VALUES (%s, %s, %s)
            """,
            (batch_name, application_id, action),
        )
        print(f"  {action:8} {application_id}  {application.business_name}")


def load_incremental(connection) -> None:
    files = sorted(INCREMENTAL_DIR.glob("*.json"))
    if not files:
        print("  No files in 02_data_engineering/incremental.")
        return
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = []
        for item in payload:
            application_id = item["application_id"]
            body = {key: value for key, value in item.items() if key != "application_id"}
            rows.append((application_id, LoanApplication(**body)))
        upsert_batch(connection, path.stem, rows)


def show_counts(connection) -> None:
    print("\nRows now in database credit, schema credit:")
    for name in INPUT_TABLES:
        count = connection.execute(f"SELECT count(*) AS n FROM credit.{name}").fetchone()["n"]
        print(f"  credit.{name:24} {count}")


def main() -> None:
    cloud = _cloud_database(os.environ.get("DATABASE_URL", ""))
    if cloud:
        step(1, "Connect to the Neon database in DATABASE_URL")
        print("  Using the connection string already set for this run.")
        step(2, "Neon already has the database. Skipping local database creation.")
    else:
        step(1, f"Connect to PostgreSQL at {PG_HOST}:{PG_PORT} as {PG_USER}")
        with psycopg.connect(ADMIN_URL, autocommit=True) as connection:
            version = connection.execute("SELECT version()").fetchone()[0]
        print(f"  {version.split(',')[0]}")

        step(2, "Create database credit")
        create_database()

    step(3, "Create schema credit and the input tables")
    applied = migrate()
    print(f"  Migrations applied this run: {applied or 'none, schema already current'}")

    with connect() as connection:
        ensure_load_log(connection)
        step(4, "Load the first three loan files")
        upsert_batch(
            connection,
            "initial",
            [(item["id"], get_sample(item["id"])) for item in SAMPLE_CATALOG],
        )
        step(5, "Load incremental files from 02_data_engineering/incremental")
        load_incremental(connection)
        connection.commit()
        show_counts(connection)

    print("\nThen run:  SELECT * FROM credit.loan_application;")
    if cloud:
        print("  Connected with the Neon DATABASE_URL for this run.")
    else:
        print(f"  Host {PG_HOST}   Port {PG_PORT}   Database {PG_DATABASE}   User {PG_USER}")


if __name__ == "__main__":
    main()
