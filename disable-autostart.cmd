@echo off
setlocal
cd /d "%~dp0"
if exist "CodexQuotaWidget.exe" (
  start "" /wait "%~dp0CodexQuotaWidget.exe" --autostart disable
) else (
  where py >nul 2>&1
  if errorlevel 1 (
    python -B widget.py --autostart disable
  ) else (
    py -3 -B widget.py --autostart disable
  )
)
if errorlevel 1 goto failed
echo Startup entry removed or restored to its previous value.
echo Exit the running widget from its right-click menu if needed.
pause
exit /b 0
:failed
echo Could not change startup. Another installation may own the current entry.
pause
exit /b 1
