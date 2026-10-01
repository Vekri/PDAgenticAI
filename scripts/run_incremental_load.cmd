@echo off
cd /d "C:\Users\Raja Reddy\Desktop\PDAgenticAI"
".venv\Scripts\python.exe" "10_schedule_and_deploy\scheduled_incremental_load.py" >> "C:\Users\Raja Reddy\Desktop\credit-inbox\schedule.log" 2>&1
