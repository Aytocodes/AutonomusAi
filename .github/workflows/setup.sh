#!/bin/bash
# =============================================================================
# setup.sh -- AutonomusAI VPS Setup Script
# Run once on a fresh Oracle Cloud Ubuntu 22.04 instance.
# Usage: chmod +x setup.sh && sudo ./setup.sh
# =============================================================================

set -e  # Exit on any error

BOT_DIR="/home/ubuntu/AutonomusAI"
PYTHON="python3"

echo "=============================================="
echo "  AutonomusAI VPS Setup"
echo "=============================================="

# --- System update ---
echo "[1/8] Updating system packages..."
apt-get update -qq && apt-get upgrade -y -qq

# --- Python & pip ---
echo "[2/8] Installing Python 3, pip, venv..."
apt-get install -y -qq python3 python3-pip python3-venv git curl wget unzip screen tmux

# --- Wine (required to run MT5 on Linux) ---
echo "[3/8] Installing Wine for MT5..."
dpkg --add-architecture i386
wget -qO- https://dl.winehq.org/wine-builds/winehq.key | apt-key add -
add-apt-repository -y "deb https://dl.winehq.org/wine-builds/ubuntu/ jammy main"
apt-get update -qq
apt-get install -y -qq --install-recommends winehq-stable
apt-get install -y -qq winetricks xvfb

# --- Virtual display (headless MT5) ---
echo "[4/8] Setting up virtual display..."
apt-get install -y -qq xvfb x11-utils

# --- Create bot directory ---
echo "[5/8] Setting up bot directory..."
mkdir -p "$BOT_DIR"
chown ubuntu:ubuntu "$BOT_DIR"

# --- Python virtual environment ---
echo "[6/8] Creating Python virtual environment..."
sudo -u ubuntu bash -c "
    cd $BOT_DIR
    $PYTHON -m venv venv
    source venv/bin/activate
    pip install --upgrade pip -q
    pip install pandas numpy python-dotenv requests -q
    echo 'MetaTrader5>=5.0.45' >> requirements.txt
    pip install MetaTrader5 -q || echo 'MT5 install skipped (install manually if needed)'
"

# --- Copy bot files ---
echo "[7/8] Copying bot files..."
# If running from the bot directory, copy all .py files
if [ -f "AutonomusAI.py" ]; then
    cp *.py "$BOT_DIR/"
    cp requirements.txt "$BOT_DIR/" 2>/dev/null || true
    cp .env "$BOT_DIR/" 2>/dev/null || true
    chown -R ubuntu:ubuntu "$BOT_DIR"
fi

# --- Install systemd service ---
echo "[8/8] Installing systemd service..."
cat > /etc/systemd/system/autonomusai.service << 'EOF'
[Unit]
Description=AutonomusAI Trading Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/AutonomusAI
Environment=DISPLAY=:99
ExecStartPre=/usr/bin/Xvfb :99 -screen 0 1024x768x24 &
ExecStart=/home/ubuntu/AutonomusAI/venv/bin/python AutonomusAI.py --mode live
Restart=always
RestartSec=30
StandardOutput=append:/home/ubuntu/AutonomusAI/bot.log
StandardError=append:/home/ubuntu/AutonomusAI/bot.log
KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable autonomusai.service

echo ""
echo "=============================================="
echo "  Setup Complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  1. Upload your bot files to: $BOT_DIR"
echo "  2. Edit .env file:  nano $BOT_DIR/.env"
echo "  3. Install MT5 via Wine (see README)"
echo "  4. Start bot:  sudo systemctl start autonomusai"
echo "  5. View logs:  tail -f $BOT_DIR/bot.log"
echo ""
