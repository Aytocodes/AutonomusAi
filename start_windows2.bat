@echo off
TITLE AutonomusAI API Server
:: Move to the directory where this batch file is located
cd /d "%~dp0"

echo Checking for node_modules...
if not exist "node_modules\" (
    echo Dependencies missing. Running npm install...
    npm install
)

echo Starting server on port 8000 for autonomud.ai...
set PORT=8000
node server.js
pause
