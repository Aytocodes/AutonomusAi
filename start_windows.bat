@echo off
title AutonomusAI Web Trader
TITLE AutonomusAI API Server
:: Move to the directory where this batch file is located
cd /d "%~dp0"

:: Change this path to match your actual backend folder
cd /d "C:\Users\Tshepo Ayto\OneDrive\Documents\Visual studio code projects\html+css web\AutonomusAI_Web\backend"
echo Checking for node_modules...
if not exist "node_modules\" (
    echo Dependencies missing. Running npm install...
    npm install
)

echo Starting AutonomusAI Web Trader...
echo Dashboard: http://localhost:8000 (Node.js)
echo Python Backend: http://localhost:8001
echo.

:: Run Python backend on a different port to avoid clash
start "Python Backend" python -m uvicorn main:app --host 0.0.0.0 --port 8001

echo Starting Node API on port 8000 for autonomud.ai...
set PORT=8000
node server.js
