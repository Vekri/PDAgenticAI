@echo off
cd /d "%~dp0.."
if not exist "data\inbox" mkdir "data\inbox"
".venv\Scripts\python.exe" "10_schedule_and_deploy\scheduled_incremental_load.py" >> "data\inbox\schedule.log" 2>&1
