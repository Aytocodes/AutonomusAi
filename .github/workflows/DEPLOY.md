# =============================================================================
# DEPLOY.md -- AutonomusAI Oracle Cloud VPS Deployment Guide
# =============================================================================

## STEP 1 -- Create Oracle Cloud VM

1. Go to https://cloud.oracle.com
2. Create a VM instance:
   - Image: Ubuntu 22.04
   - Shape: VM.Standard.E2.1.Micro (free tier) or better
   - Add your SSH public key
3. Open ports in Security List:
   - No inbound ports needed (bot only makes outbound connections)

---

## STEP 2 -- Connect to VPS

```bash
ssh ubuntu@YOUR_VPS_IP
```

---

## STEP 3 -- Upload Bot Files

From your Windows PC (run in PowerShell):

```powershell
$BOT_PATH = "c:\Users\Tshepo Ayto\OneDrive\Documents\Visual studio code projects\html+css web\Expert advisor"
$VPS_IP   = "YOUR_VPS_IP"

scp "$BOT_PATH\*.py"              ubuntu@${VPS_IP}:/home/ubuntu/AutonomusAI/
scp "$BOT_PATH\.env"              ubuntu@${VPS_IP}:/home/ubuntu/AutonomusAI/
scp "$BOT_PATH\requirements.txt"  ubuntu@${VPS_IP}:/home/ubuntu/AutonomusAI/
scp "$BOT_PATH\setup.sh"          ubuntu@${VPS_IP}:/home/ubuntu/AutonomusAI/
scp "$BOT_PATH\run_bot.sh"        ubuntu@${VPS_IP}:/home/ubuntu/AutonomusAI/
scp "$BOT_PATH\autonomusai.service" ubuntu@${VPS_IP}:/home/ubuntu/AutonomusAI/
scp "$BOT_PATH\*.csv"             ubuntu@${VPS_IP}:/home/ubuntu/AutonomusAI/
```

---

## STEP 4 -- Run Setup on VPS

```bash
# SSH into VPS
ssh ubuntu@YOUR_VPS_IP

# Create bot directory
mkdir -p /home/ubuntu/AutonomusAI
cd /home/ubuntu/AutonomusAI

# Make scripts executable
chmod +x setup.sh run_bot.sh

# Run setup (installs everything)
sudo ./setup.sh
```

---

## STEP 5 -- Configure .env

```bash
nano /home/ubuntu/AutonomusAI/.env
```

Fill in:
```
MT5_LOGIN=298245219
MT5_PASSWORD=your_actual_password
MT5_SERVER=Exness-MT5Real
TELEGRAM_TOKEN=your_bot_token      # optional
TELEGRAM_CHAT_ID=your_chat_id      # optional
```

Save: Ctrl+O, Enter, Ctrl+X

---

## STEP 6 -- Install MT5 via Wine

```bash
# Download MT5 installer
cd /home/ubuntu
wget https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe

# Run installer with virtual display
export DISPLAY=:99
Xvfb :99 -screen 0 1024x768x24 &
wine mt5setup.exe

# Follow the installer GUI (use VNC or X11 forwarding to see it)
# OR use a pre-configured Wine prefix
```

**Easier alternative -- use a broker that supports Python API directly:**
The bot also works with any REST API broker. Replace MarketDataHandler
with an HTTP-based data source if MT5 on Wine is too complex.

---

## STEP 7 -- Install Python Dependencies

```bash
cd /home/ubuntu/AutonomusAI
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## STEP 8 -- Test the Bot

```bash
cd /home/ubuntu/AutonomusAI
source venv/bin/activate

# Test backtest first (no MT5 needed)
python AutonomusAI.py --mode backtest --csv xauusd_m15.csv

# Test live connection
python AutonomusAI.py --mode live
```

---

## STEP 9 -- Run with systemd (auto-start on reboot)

```bash
# Install service
sudo cp /home/ubuntu/AutonomusAI/autonomusai.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable autonomusai
sudo systemctl start autonomusai

# Check status
sudo systemctl status autonomusai
```

---

## STEP 10 -- Run with screen (simpler alternative)

```bash
# Start in a screen session
screen -S autonomusai
cd /home/ubuntu/AutonomusAI
./run_bot.sh

# Detach from screen (bot keeps running)
# Press: Ctrl+A then D

# Reattach later
screen -r autonomusai
```

---

## MONITORING COMMANDS

```bash
# Watch live logs
tail -f /home/ubuntu/AutonomusAI/bot.log

# Last 50 lines
tail -50 /home/ubuntu/AutonomusAI/bot.log

# Search for trades
grep "Trade placed" /home/ubuntu/AutonomusAI/bot.log

# Search for errors
grep "ERROR" /home/ubuntu/AutonomusAI/bot.log

# Check if bot is running
ps aux | grep AutonomusAI

# Restart bot
sudo systemctl restart autonomusai

# Stop bot
sudo systemctl stop autonomusai

# View systemd logs
sudo journalctl -u autonomusai -f
```

---

## TELEGRAM ALERTS SETUP (optional but recommended)

1. Open Telegram, search for @BotFather
2. Send: /newbot
3. Follow instructions, copy the TOKEN
4. Search for @userinfobot, send /start, copy your CHAT_ID
5. Add both to .env file

You will receive alerts for:
- Bot start/stop
- Every trade placed
- MT5 disconnections
- Critical errors

---

## FILE STRUCTURE ON VPS

```
/home/ubuntu/AutonomusAI/
├── AutonomusAI.py          <- Main bot
├── config.py               <- Strategy settings
├── logger.py               <- Logging system
├── market_data.py          <- MT5 data handler
├── trend_engine.py         <- H1 trend analysis
├── crt_detector.py         <- CRT zone detection
├── liquidity_engine.py     <- Sweep detection
├── order_block_engine.py   <- OB + FVG detection
├── risk_manager.py         <- Position sizing
├── execution_engine.py     <- Trade execution
├── strategy_engine.py      <- Signal combiner
├── backtester.py           <- Backtest engine
├── .env                    <- Secrets (never share)
├── requirements.txt        <- Dependencies
├── run_bot.sh              <- Start script
├── setup.sh                <- Install script
├── autonomusai.service     <- systemd service
├── bot.log                 <- Live log file
└── *.csv                   <- Historical data
```
