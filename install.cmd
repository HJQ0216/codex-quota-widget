@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
if not exist "runtime\tmp" mkdir "runtime\tmp"
set "TEMP=%~dp0runtime\tmp"
set "TMP=%TEMP%"
where py >nul 2>&1
if errorlevel 1 (set "WIDGET_PYTHON=python") else (set "WIDGET_PYTHON=py -3")
%WIDGET_PYTHON% -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11 or newer is required'"
if errorlevel 1 exit /b 1
%WIDGET_PYTHON% -B -m pip install --disable-pip-version-check --no-compile --target lib --cache-dir runtime\pip-cache -r requirements.txt
if errorlevel 1 exit /b 1
echo Installed. Run start.cmd to launch the widget.
