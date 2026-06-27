@echo off
chcp 65001 >nul
title 岁己SUI 微博监控 - 窗口关闭即停止
echo ============================================
echo     岁己SUI 微博在线状态监控
echo     Telegram: @sui_weibo_bot
echo     WebUI: http://localhost:8765
echo     (窗口开着 = 运行中，关了 = 停止)
echo ============================================
echo.

cd /d "%~dp0"
C:\Users\Tsing\AppData\Local\Programs\Python\Python310\python.exe -X utf8 app.py
pause
