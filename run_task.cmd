@echo off
REM Scheduled-task wrapper for the trading pipeline.
REM Usage: run_task.cmd <cycle|check|status|reconcile|kill> [config-file]
REM   config-file (optional 2nd arg) = config JSON for the A/B arm (separate journal)
REM     e.g. run_task.cmd cycle config_ab_mhm.json  -> MHM-gate arm, logs to scheduled_ab.log
REM NOTE: keep this file ASCII-only with CRLF line endings (cmd.exe requirement).
setlocal
set CFG=%~2
cd /d "%~dp0"
if "%CFG%"=="" (
  python main.py %1 >> logs\scheduled.log 2>&1
) else (
  python main.py --config "%CFG%" %1 >> logs\scheduled_ab.log 2>&1
)
endlocal & exit /b %errorlevel%
