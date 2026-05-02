#!/usr/bin/env bash
# ── Bot Management Helper ────────────────────────────────────────────────────
# Usage: ./manage.sh [start|stop|restart|logs|status|update]

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE="ytdlp-bot"
VENV="$BOT_DIR/venv"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RESET='\033[0m'

case "${1:-help}" in
    start)
        systemctl start "$SERVICE"
        echo -e "${GREEN}✅ Bot started${RESET}"
        ;;
    stop)
        systemctl stop "$SERVICE"
        echo -e "${YELLOW}⏹  Bot stopped${RESET}"
        ;;
    restart)
        systemctl restart "$SERVICE"
        echo -e "${GREEN}🔄 Bot restarted${RESET}"
        ;;
    status)
        systemctl status "$SERVICE" --no-pager -l
        ;;
    logs)
        journalctl -u "$SERVICE" -f --no-pager
        ;;
    tail)
        tail -f "$BOT_DIR/bot.log"
        ;;
    update)
        echo -e "${CYAN}🔄 Updating yt-dlp and dependencies...${RESET}"
        source "$VENV/bin/activate"
        pip install --upgrade yt-dlp python-telegram-bot -q
        echo -e "${GREEN}✅ Updated! Restarting...${RESET}"
        systemctl restart "$SERVICE"
        systemctl status "$SERVICE" --no-pager
        ;;
    clean)
        echo -e "${YELLOW}🧹 Cleaning downloads folder...${RESET}"
        count=$(find "$BOT_DIR/downloads" -type f | wc -l)
        rm -f "$BOT_DIR/downloads"/*
        echo -e "${GREEN}✅ Removed $count files${RESET}"
        ;;
    help|*)
        echo ""
        echo -e "${CYAN}  YT-DLP Bot Manager${RESET}"
        echo ""
        echo "  Usage: ./manage.sh <command>"
        echo ""
        echo "  Commands:"
        echo "    start    — Start the bot"
        echo "    stop     — Stop the bot"
        echo "    restart  — Restart the bot"
        echo "    status   — Show service status"
        echo "    logs     — Live systemd logs"
        echo "    tail     — Tail bot.log file"
        echo "    update   — Update yt-dlp & deps"
        echo "    clean    — Clear downloads folder"
        echo ""
        ;;
esac
