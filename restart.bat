@echo off
title AutonomusAI Server

:: Kill existing process on port 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 2^>nul') do taskkill /PID %%a /F >nul 2>&1

:: Start server
cd /d "C:\Users\Tshepo Ayto\OneDrive\Documents\Visual studio code projects\html+css web\AutonomusAI_Web\backend"
echo Starting AutonomusAI...
echo Dashboard: http://localhost:8000
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8000
pause
