@echo off
setlocal
cd /d "%~dp0"
if exist "CodexQuotaWidget.exe" (
  start "" /wait "%~dp0CodexQuotaWidget.exe" --autostart enable
  if errorlevel 1 goto failed
  start "" "%~dp0CodexQuotaWidget.exe"
) else (
  where py >nul 2>&1
  if errorlevel 1 (
    python -B widget.py --autostart enable
  ) else (
    py -3 -B widget.py --autostart enable
  )
  if errorlevel 1 goto failed
  call start.cmd
)
echo Enabled. The widget will wait for Codex after Windows sign-in.
echo To undo, run disable-autostart.cmd.
pause
exit /b 0
:failed
echo Failed to enable startup. Check the folder is writable and the path is short.
pause
exit /b 1
