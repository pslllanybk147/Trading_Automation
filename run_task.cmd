@echo off
REM Scheduled-task wrapper for the trading pipeline.
REM Usage: run_task.cmd <cycle|check|status|reconcile|kill>
cd /d "%~dp0"
python main.py %1 >> logs\scheduled.log 2>&1
exit /b %errorlevel%
