# 🎬 YT-DLP Telegram Bot

A feature-rich Telegram bot for downloading YouTube videos and audio with playlist support, quality selection, progress tracking, and beautiful UI.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🎵 Audio Download | Best quality MP3 (192kbps) with embedded thumbnail & metadata |
| 🎬 Video Download | Up to 1080p MP4 |
| 🎞️ Quality Selector | Choose exact resolution (144p–1080p) with file size preview |
| 📋 Playlist Support | Download full playlists as audio or video, one-by-one |
| ⬇️ Progress Bar | Live download progress with speed & ETA |
| 🔐 Cookie Support | Pre-loaded YouTube cookies for age-restricted & private content |
| 👑 Admin Commands | Stats, uptime, active downloads info |
| 🚫 Concurrency Limits | Per-user and global download limits |
| 🧹 Auto Cleanup | Automatically deletes temp files after sending |
| 🔁 Systemd Service | Runs as a persistent background service with auto-restart |

---

## 🚀 Quick Install (Ubuntu VPS)

```bash
# 1. Clone or copy the bot files to your server
git clone https://github.com/itisak-51/yt-dlp.git && cd ~/yt-dlp

# 2. Set your Bot Token in .env
nano .env
# Set: BOT_TOKEN=your_token_here
# Set: ADMIN_IDS=your_telegram_user_id

# 3. Run the installer (as root or with sudo)
chmod +x install.sh
sudo ./install.sh
```

---

## ⚙️ Configuration (.env)

```env
BOT_TOKEN=1234567890:ABCdef...       # From @BotFather
ADMIN_IDS=123456789                  # Your Telegram user ID
DOWNLOAD_DIR=./downloads             # Where files are saved temporarily
COOKIES_FILE=./cookies.txt           # YouTube cookies
MAX_CONCURRENT_PER_USER=2            # Max downloads per user at once
MAX_CONCURRENT_TOTAL=5               # Global max concurrent downloads
MAX_FILE_SIZE_MB=50                  # Telegram limit (50MB for bots)
AUTO_DELETE_FILES=true               # Delete files after upload
RESTRICTED_MODE=false                # Set true to whitelist users only
ALLOWED_USERS=                       # Comma-separated IDs for restricted mode
PROXY=                               # Optional: socks5://user:pass@host:port
```

---

## 📋 Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message & feature overview |
| `/help` | Detailed usage instructions |
| `/stats` | Download statistics & bot uptime |
| `/cancel` | Cancel your active download |

---

## 🛠️ Management

```bash
./manage.sh start      # Start bot
./manage.sh stop       # Stop bot
./manage.sh restart    # Restart bot
./manage.sh status     # Show status
./manage.sh logs       # Live logs (Ctrl+C to exit)
./manage.sh update     # Update yt-dlp to latest version
./manage.sh clean      # Clear downloads folder
```

---

## 📁 File Structure

```
ytdlp-bot/
├── bot.py           ← Main bot code
├── cookies.txt      ← YouTube cookies (already loaded)
├── .env             ← Configuration
├── requirements.txt ← Python dependencies
├── install.sh       ← Automated installer
├── manage.sh        ← Management helper
├── downloads/       ← Temporary download folder (auto-created)
├── venv/            ← Python virtual environment (auto-created)
└── bot.log          ← Bot log file
```

---

## 🍪 Cookies

Your cookies are already saved in `cookies.txt`. They allow downloading:
- Age-restricted videos
- Members-only content
- Private videos you have access to

To refresh cookies, export fresh ones from your browser (use the "Cookie-Editor" extension) and replace `cookies.txt`.

---

## ⚠️ Notes

- Telegram bots can only send files up to **50MB**. Large videos will be rejected with a warning.
- For larger files, consider splitting or choosing a lower quality.
- yt-dlp is updated frequently; run `./manage.sh update` periodically.
- The bot automatically retries on network errors.

---

## 📦 Dependencies

- `python-telegram-bot` 20.x
- `yt-dlp` (latest)
- `ffmpeg` (system package)
- `atomicparsley` (for thumbnail embedding)
- 
