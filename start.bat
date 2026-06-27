@echo off
chcp 65001 >nul
title 岁己SUI 微博监控
echo ============================================
echo     岁己SUI 微博在线状态监控
echo ============================================
echo.
echo     Telegram Bot: @sui_weibo_bot
echo     命令: /status /today /stats /log /daily /hourly
echo.
echo     关闭此窗口 = 停止监控
echo ============================================
echo.

cd /d "%~dp0"

REM 查找 Python
set PY=
if exist "C:\Users\Tsing\AppData\Local\Programs\Python\Python310\python.exe" set PY=C:\Users\Tsing\AppData\Local\Programs\Python\Python310\python.exe
if "%PY%"=="" where python >nul 2>&1 && set PY=python
if "%PY%"=="" where python3 >nul 2>&1 && set PY=python3
if "%PY%"=="" (
    echo 错误: 找不到 Python，请安装 Python 3.8+
    pause
    exit /b 1
)

echo [启动] Python: %PY%
echo.

%PY% -X utf8 app.py
pause
