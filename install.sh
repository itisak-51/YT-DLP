#!/usr/bin/env bash
# ============================================================
#   🚀  YT-DLP Telegram Bot — Ubuntu VPS Installer
# ============================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

OK()   { echo -e "${GREEN}✅  $*${RESET}"; }
WARN() { echo -e "${YELLOW}⚠️   $*${RESET}"; }
ERR()  { echo -e "${RED}❌  $*${RESET}"; exit 1; }
INFO() { echo -e "${CYAN}ℹ️   $*${RESET}"; }
HEAD() { echo -e "\n${BOLD}${BLUE}══════════════════════════════════════${RESET}"; echo -e "${BOLD}${BLUE}  $*${RESET}"; echo -e "${BOLD}${BLUE}══════════════════════════════════════${RESET}\n"; }

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="ytdlp-bot"
VENV_DIR="$BOT_DIR/venv"

HEAD "🎬  YT-DLP Telegram Bot Installer"

# ── Check root ────────────────────────────────────────────────────────────────
if [[ $EUID -eq 0 ]]; then
    WARN "Running as root. Consider using a non-root user for security."
fi

# ── System packages ───────────────────────────────────────────────────────────
HEAD "1. Installing System Packages"

apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    ffmpeg \
    curl wget git \
    ca-certificates \
    atomicparsley

OK "System packages installed"
echo ""
INFO "Python: $(python3 --version)"
INFO "FFmpeg: $(ffmpeg -version 2>&1 | head -1)"

# ── Python venv ───────────────────────────────────────────────────────────────
HEAD "2. Setting Up Python Environment"

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    OK "Virtual environment created"
else
    INFO "Virtual environment already exists"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
pip install -r "$BOT_DIR/requirements.txt" -q
OK "Python dependencies installed"

# ── Create downloads dir ──────────────────────────────────────────────────────
HEAD "3. Setting Up Directories"

mkdir -p "$BOT_DIR/downloads"
chmod 755 "$BOT_DIR/downloads"
OK "Downloads directory ready"

# ── Check .env ────────────────────────────────────────────────────────────────
HEAD "4. Configuration Check"

ENV_FILE="$BOT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    ERR ".env file not found! Create it from .env.example"
fi

# Check token is set
if grep -q "YOUR_BOT_TOKEN_HERE" "$ENV_FILE"; then
    WARN "BOT_TOKEN is not set in .env!"
    echo ""
    read -rp "Enter your Telegram Bot Token: " TOKEN
    if [ -n "$TOKEN" ]; then
        sed -i "s/YOUR_BOT_TOKEN_HERE/$TOKEN/" "$ENV_FILE"
        OK "Bot token saved"
    else
        ERR "Bot token is required!"
    fi
else
    OK "Bot token is configured"
fi

# Check admin IDs
if grep -q "^ADMIN_IDS=123456789" "$ENV_FILE"; then
    WARN "Admin ID is still default (123456789)"
    read -rp "Enter your Telegram User ID (leave blank to skip): " ADMIN_ID
    if [ -n "$ADMIN_ID" ]; then
        sed -i "s/^ADMIN_IDS=123456789/ADMIN_IDS=$ADMIN_ID/" "$ENV_FILE"
        OK "Admin ID saved"
    fi
fi

# Check cookies
if [ -f "$BOT_DIR/cookies.txt" ]; then
    OK "Cookies file found"
else
    WARN "cookies.txt not found — some age-restricted content may fail"
fi

# ── Systemd service ───────────────────────────────────────────────────────────
HEAD "5. Setting Up Systemd Service"

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=YT-DLP Telegram Bot
After=network.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${BOT_DIR}
ExecStart=${VENV_DIR}/bin/python ${BOT_DIR}/bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
OK "Systemd service created and enabled"

# ── Start the bot ─────────────────────────────────────────────────────────────
HEAD "6. Starting the Bot"

if systemctl is-active --quiet "${SERVICE_NAME}"; then
    systemctl restart "${SERVICE_NAME}"
    OK "Bot restarted"
else
    systemctl start "${SERVICE_NAME}"
    OK "Bot started"
fi

sleep 2

# ── Final status ──────────────────────────────────────────────────────────────
HEAD "✅  Installation Complete!"

echo -e "${GREEN}${BOLD}Your bot is now running!${RESET}\n"
echo -e "📋 ${BOLD}Useful commands:${RESET}"
echo -e "   ${CYAN}systemctl status ${SERVICE_NAME}${RESET}   — check status"
echo -e "   ${CYAN}systemctl restart ${SERVICE_NAME}${RESET}  — restart"
echo -e "   ${CYAN}systemctl stop ${SERVICE_NAME}${RESET}     — stop"
echo -e "   ${CYAN}journalctl -u ${SERVICE_NAME} -f${RESET}   — live logs"
echo ""
echo -e "📁 Bot directory: ${YELLOW}${BOT_DIR}${RESET}"
echo -e "📄 Logs:          ${YELLOW}${BOT_DIR}/bot.log${RESET}"
echo ""

systemctl status "${SERVICE_NAME}" --no-pager -l || true
