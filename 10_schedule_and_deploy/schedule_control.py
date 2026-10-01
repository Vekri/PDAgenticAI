"""Run the initial load and the incremental load, and save a Windows schedule."""

from __future__ import annotations

import contextlib
import io
import subprocess
from datetime import date, datetime, time
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from app.config import INBOX, ROOT

TASK_NAME = "CreditIncrementalLoad"
LOADER = ROOT / "scripts" / "run_incremental_load.cmd"
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _load(path: Path, name: str):
    spec = spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _capture(module_path: Path, module_name: str) -> str:
    module = _load(module_path, module_name)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        module.main()
    return buffer.getvalue().strip() or "Finished."


def run_initial_load() -> str:
    return _capture(ROOT / "02_data_engineering" / "load_credit_inputs.py", "load_credit_inputs_desk")


def run_incremental_load() -> str:
    return _capture(ROOT / "10_schedule_and_deploy" / "scheduled_incremental_load.py", "scheduled_incremental_load_desk")


def inbox_waiting() -> list[str]:
    if not INBOX.exists():
        return []
    return sorted(path.name for path in INBOX.glob("*.json") if path.is_file())


def inbox_loaded() -> list[str]:
    folder = INBOX / "loaded"
    if not folder.exists():
        return []
    return sorted(path.name for path in folder.glob("*.json"))


def project_incremental_files() -> list[str]:
    folder = ROOT / "02_data_engineering" / "incremental"
    return sorted(path.name for path in folder.glob("*.json"))


def _powershell(script: str) -> str:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        raise RuntimeError(output.strip() or "Windows could not save the schedule.")
    return output.strip()


def task_status() -> str:
    script = f"""
$task = Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue
if (-not $task) {{ 'No Windows schedule is saved. Incremental load runs only when you press the button.'; exit 0 }}
$info = $task | Get-ScheduledTaskInfo
"State: $($task.State)"
"Next run: $($info.NextRunTime)"
"Last run: $($info.LastRunTime)"
"Last result code: $($info.LastTaskResult)"
"""
    return _powershell(script)


def save_schedule(mode: str, clock: time, on_date: date | None, weekday: str, every_minutes: int) -> str:
    if mode == "Manual only":
        script = f"""
$task = Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue
if ($task) {{ Disable-ScheduledTask -TaskName '{TASK_NAME}' | Out-Null; 'Schedule paused. Use Run incremental load now.' }}
else {{ 'Manual only. No Windows schedule is active.' }}
"""
        return _powershell(script)

    stamp = clock.strftime("%H:%M")
    setup = ""
    if mode == "Every day":
        trigger = f"New-ScheduledTaskTrigger -Daily -At '{stamp}'"
    elif mode == "One weekday":
        trigger = f"New-ScheduledTaskTrigger -Weekly -DaysOfWeek {weekday} -At '{stamp}'"
    elif mode == "One date and time":
        if on_date is None:
            raise ValueError("Choose a date.")
        moment = datetime.combine(on_date, clock).strftime("%Y-%m-%dT%H:%M:%S")
        trigger = f"New-ScheduledTaskTrigger -Once -At '{moment}'"
    elif mode == "Every few minutes":
        minutes = max(1, int(every_minutes))
        setup = "$start = Get-Date"
        trigger = (
            "New-ScheduledTaskTrigger -Once -At $start "
            f"-RepetitionInterval (New-TimeSpan -Minutes {minutes}) "
            "-RepetitionDuration (New-TimeSpan -Days 3650)"
        )
    else:
        raise ValueError(f"Unknown schedule '{mode}'.")

    argument = f'/c "{LOADER}"'
    script = f"""
{setup}
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '{argument}'
$trigger = {trigger}
Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $action -Trigger $trigger -Force | Out-Null
Enable-ScheduledTask -TaskName '{TASK_NAME}' | Out-Null
'Saved {mode} for {TASK_NAME}.'
"""
    return _powershell(script)
