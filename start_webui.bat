@echo off
title Suisui WebUI
echo ============================================
echo   Suisui SUI - Weibo Monitor WebUI
echo ============================================
echo.
echo   Open in browser: http://localhost:8765
echo   (Close this window = stop WebUI)
echo ============================================
echo.

cd /d "%~dp0"

set PY=
if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" set PY=%LOCALAPPDATA%\Programs\Python\Python310\python.exe
if not defined PY ( where python >nul 2>&1 && set PY=python )
if not defined PY ( where python3 >nul 2>&1 && set PY=python3 )
if not defined PY (
    echo [ERROR] Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

echo [START] Python: %PY%
echo.

%PY% -X utf8 web_ui.py
pause
