@echo off
title AutonomusAI - Live Trading Bot
color 0A
echo ================================================
echo   AutonomusAI Live Trading Bot - Starting...
echo ================================================
echo.

cd /d "c:\Users\Tshepo Ayto\OneDrive\Documents\Visual studio code projects\html+css web\Expert advisor"

:start
echo [%date% %time%] Starting AutonomusAI...
python AutonomusAI.py --mode live --symbol XAUUSDm --risk 0.01
echo.
echo [%date% %time%] Bot stopped. Restarting in 10 seconds...
timeout /t 10
goto start
