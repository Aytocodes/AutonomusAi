#!/bin/bash
# =============================================================================
# run_bot.sh -- Start AutonomusAI on VPS
# Usage: chmod +x run_bot.sh && ./run_bot.sh
# =============================================================================

BOT_DIR="/home/ubuntu/AutonomusAI"
VENV="$BOT_DIR/venv/bin/python"
LOG="$BOT_DIR/bot.log"
DISPLAY_NUM=99

cd "$BOT_DIR" || { echo "Bot directory not found: $BOT_DIR"; exit 1; }

# --- Start virtual display if not running ---
if ! pgrep -x Xvfb > /dev/null; then
    echo "[run_bot] Starting virtual display :$DISPLAY_NUM..."
    Xvfb :$DISPLAY_NUM -screen 0 1024x768x24 &
    sleep 2
fi
export DISPLAY=:$DISPLAY_NUM

# --- Activate venv ---
source "$BOT_DIR/venv/bin/activate"

echo "[run_bot] Starting AutonomusAI..."
echo "[run_bot] Logs: $LOG"
echo "[run_bot] Press Ctrl+C to stop"
echo ""

# Run with auto-restart loop
while true; do
    echo "$(date '+%Y-%m-%d %H:%M:%S') | INFO     | Bot starting..." >> "$LOG"
    $VENV AutonomusAI.py --mode live
    EXIT_CODE=$?
    echo "$(date '+%Y-%m-%d %H:%M:%S') | WARNING  | Bot exited (code $EXIT_CODE). Restarting in 30s..." >> "$LOG"
    echo "[run_bot] Bot stopped (exit $EXIT_CODE). Restarting in 30s..."
    sleep 30
done
