#!/bin/bash
# =============================================================================
# setup.sh -- AutonomusAI Web Platform VPS Setup
# Ubuntu 22.04 / Oracle Cloud
# Usage: chmod +x setup.sh && sudo ./setup.sh
# =============================================================================

set -e

APP_DIR="/home/ubuntu/autonomusai"
BACKEND="$APP_DIR/backend"
VENV="$APP_DIR/venv"
SERVICE_NAME="a2bot"

echo "=============================================="
echo "  AutonomusAI Web Platform Setup"
echo "=============================================="

# 1. System packages
echo "[1/7] Updating system..."
apt-get update -qq && apt-get upgrade -y -qq
apt-get install -y -qq python3 python3-pip python3-venv git curl wget unzip \
    xvfb x11-utils net-tools ufw

# 2. Wine for MetaTrader 5 on Linux
echo "[2/7] Installing Wine (for MT5)..."
dpkg --add-architecture i386
wget -qO- https://dl.winehq.org/wine-builds/winehq.key | gpg --dearmor \
    -o /usr/share/keyrings/winehq-archive.key
echo "deb [arch=amd64,i386 signed-by=/usr/share/keyrings/winehq-archive.key] \
    https://dl.winehq.org/wine-builds/ubuntu/ jammy main" \
    > /etc/apt/sources.list.d/winehq.list
apt-get update -qq
apt-get install -y -qq --install-recommends winehq-stable winetricks || \
    echo "Wine install failed — install MT5 manually if needed"

# 3. App directory
echo "[3/7] Creating app directory..."
mkdir -p "$BACKEND"
chown -R ubuntu:ubuntu "$APP_DIR"

# 4. Copy files
echo "[4/7] Copying project files..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$SCRIPT_DIR/backend" ]; then
    cp -r "$SCRIPT_DIR/backend/." "$BACKEND/"
    cp -r "$SCRIPT_DIR/frontend" "$APP_DIR/" 2>/dev/null || true
    chown -R ubuntu:ubuntu "$APP_DIR"
else
    echo "  WARNING: Run this script from the AutonomusAI_Web project root."
fi

# 5. Python virtual environment + dependencies
echo "[5/7] Installing Python dependencies..."
sudo -u ubuntu bash -c "
    python3 -m venv $VENV
    $VENV/bin/pip install --upgrade pip -q
    $VENV/bin/pip install -r $BACKEND/requirements.txt -q
"

# 6. .env file (create if missing)
if [ ! -f "$BACKEND/.env" ]; then
    echo "[6/7] Creating default .env..."
    cat > "$BACKEND/.env" << 'ENVEOF'
SECRET_KEY=change-this-to-a-random-secret-key-in-production
MEMORY_LIMIT_MB=512
ENVEOF
    chown ubuntu:ubuntu "$BACKEND/.env"
    chmod 600 "$BACKEND/.env"
    echo "  !! Edit $BACKEND/.env and set a strong SECRET_KEY !!"
else
    echo "[6/7] .env already exists — skipping"
fi

# 7. systemd service
echo "[7/7] Installing systemd service..."
cp "$SCRIPT_DIR/a2bot.service" /etc/systemd/system/a2bot.service
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

# Firewall: allow port 8000
ufw allow 8000/tcp 2>/dev/null || true

echo ""
echo "=============================================="
echo "  Setup Complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  1. Edit .env:        nano $BACKEND/.env"
echo "  2. Start service:    sudo systemctl start a2bot"
echo "  3. View status:      sudo systemctl status a2bot"
echo "  4. View logs:        sudo journalctl -u a2bot -f"
echo "  5. Dashboard:        http://<your-server-ip>:8000"
echo ""
