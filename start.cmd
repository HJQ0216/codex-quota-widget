@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
where pyw >nul 2>&1
if not errorlevel 1 (
  start "" pyw -3 -B "%~dp0widget.py"
  exit /b
)
where pythonw >nul 2>&1
if not errorlevel 1 (
  start "" pythonw -B "%~dp0widget.py"
  exit /b
)
echo Python 3.11+ with Tk is required. Read README.md or use the portable release.
pause
