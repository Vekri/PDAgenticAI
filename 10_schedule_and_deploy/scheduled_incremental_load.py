"""Pick up new loan files from the desktop inbox and load them on a schedule.

Drop one JSON file per batch into:
    C:\\Users\\Raja Reddy\\Desktop\\credit-inbox

Each file is a list of loan applications, or one application object.
The Windows task CreditIncrementalLoad runs this script every 15 minutes.
A file is moved to credit-inbox\\loaded after the rows are stored and scored.
Each pickup is written to credit.schedule_capture.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INBOX = Path(r"C:\Users\Raja Reddy\Desktop\credit-inbox")
LOADED = INBOX / "loaded"
PG_USER = "postgres"
PG_PASSWORD = "postgre"
if not os.environ.get("DATABASE_URL", "").strip():
    os.environ["DATABASE_URL"] = f"postgresql://{PG_USER}:{PG_PASSWORD}@localhost:5432/credit"
    os.environ["PD_ENV"] = "local"

from app.data_engineering.warehouse import decide_stored, upsert_sources
from app.platform.postgres import connect, migrate
from app.schemas import LoanApplication


def ensure_folders() -> None:
    INBOX.mkdir(parents=True, exist_ok=True)
    LOADED.mkdir(parents=True, exist_ok=True)


def read_applications(path: Path) -> list[tuple[str, LoanApplication]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = [payload]
    rows = []
    for item in payload:
        application_id = str(item["application_id"]).strip()
        body = {key: value for key, value in item.items() if key != "application_id"}
        rows.append((application_id, LoanApplication(**body)))
    return rows


def capture(connection, path: Path, application_id: str | None, action: str, detail: str, result=None) -> None:
    connection.execute(
        """
        INSERT INTO credit.schedule_capture (
            source_path, file_name, application_id, load_action,
            recommendation, pd_display, run_id, detail
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            str(INBOX),
            path.name,
            application_id,
            action,
            None if result is None else result.recommendation,
            None if result is None else result.pd_display,
            None if result is None else result.run_id,
            detail,
        ),
    )


def load_file(path: Path) -> int:
    rows = read_applications(path)
    with connect() as connection:
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
                (path.stem, application_id, action),
            )
            connection.commit()
            result = decide_stored(application_id, use_llm=False)
            with connect() as scored:
                capture(scored, path, application_id, action, "Picked up from the desktop inbox and scored.", result)
                scored.commit()
            print(f"{action:8} {application_id:12} {result.recommendation:8} {result.pd_display}")
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    shutil.move(str(path), LOADED / f"{stamp}_{path.name}")
    return len(rows)


def main() -> None:
    ensure_folders()
    migrate()
    files = sorted(path for path in INBOX.glob("*.json") if path.is_file())
    if not files:
        print(f"No new JSON files in {INBOX}")
        return
    total = 0
    for path in files:
        try:
            total += load_file(path)
        except Exception as exc:
            with connect() as connection:
                capture(connection, path, None, "failed", traceback.format_exc().splitlines()[-1])
                connection.commit()
            print(f"failed   {path.name}  {exc}")
    print(f"Loaded {total} application(s) from {len(files)} file(s).")


if __name__ == "__main__":
    main()
