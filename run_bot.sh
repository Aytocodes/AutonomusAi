#!/bin/bash
# =============================================================================
# run_bot.sh -- Manual start fallback (use systemd in production)
# =============================================================================

APP_DIR="/home/ubuntu/autonomusai"
BACKEND="$APP_DIR/backend"
VENV="$APP_DIR/venv"
LOG="$BACKEND/bot.log"

# Start virtual display for MT5
if ! pgrep -x Xvfb > /dev/null; then
    Xvfb :99 -screen 0 1024x768x24 &
    echo "Xvfb started"
fi
export DISPLAY=:99

cd "$BACKEND"

echo "Starting AutonomusAI Web Trader..."
echo "Logs: $LOG"
echo "Dashboard: http://0.0.0.0:8000"
echo "Press Ctrl+C to stop"
echo ""

"$VENV/bin/uvicorn" main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --loop asyncio \
    --log-level info \
    2>&1 | tee -a "$LOG"
