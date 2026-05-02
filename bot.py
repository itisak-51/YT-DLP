#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║         🎬  YT-DLP Telegram Bot  🎵                     ║
║   Video • Audio • Playlists • Beautiful UI               ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import re
import sys
import time
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Optional

import yt_dlp
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode, ChatAction
from telegram.error import TelegramError

# ─── Load Environment ────────────────────────────────────────────────────────
load_dotenv()

BOT_TOKEN         = os.getenv("BOT_TOKEN", "")
ADMIN_IDS         = [int(x) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip().isdigit()]
DOWNLOAD_DIR      = Path(os.getenv("DOWNLOAD_DIR", "./downloads"))
COOKIES_FILE      = Path(os.getenv("COOKIES_FILE", "./cookies.txt"))
MAX_CONCURRENT    = int(os.getenv("MAX_CONCURRENT_TOTAL", "5"))
MAX_PER_USER      = int(os.getenv("MAX_CONCURRENT_PER_USER", "2"))
MAX_FILE_MB       = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
AUTO_DELETE       = os.getenv("AUTO_DELETE_FILES", "true").lower() == "true"
RESTRICTED_MODE   = os.getenv("RESTRICTED_MODE", "false").lower() == "true"
ALLOWED_USERS     = [int(x) for x in os.getenv("ALLOWED_USERS", "").split(",") if x.strip().isdigit()]
PROXY             = os.getenv("PROXY", "")

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("bot.log", encoding="utf-8")],
)
logger = logging.getLogger("ytdlp_bot")

# ─── Global State ────────────────────────────────────────────────────────────
active_downloads: dict[int, dict] = {}
user_download_count: dict[int, int] = defaultdict(int)
download_semaphore = asyncio.Semaphore(MAX_CONCURRENT)
bot_stats = {"total_downloads": 0, "total_audio": 0, "total_video": 0,
             "total_playlist": 0, "start_time": datetime.now()}

# ─── Emojis ─────────────────────────────────────────────────────────────────
E = {
    "dl": "⬇️", "audio": "🎵", "video": "🎬", "list": "📋", "check": "✅", "cross": "❌",
    "wait": "⏳", "rocket": "🚀", "warn": "⚠️", "info": "ℹ️", "size": "📦",
    "time": "⏱️", "bar": "▓", "bar_e": "░", "cancel": "🚫", "quality": "🎞️",
}

PROGRESS_BAR_LEN = 10

def make_progress_bar(percent: float) -> str:
    filled = int(percent / 100 * PROGRESS_BAR_LEN)
    return E["bar"] * filled + E["bar_e"] * (PROGRESS_BAR_LEN - filled)

def fmt_size(bytes_: int) -> str:
    if bytes_ < 1024: return f"{bytes_} B"
    elif bytes_ < 1048576: return f"{bytes_/1024:.1f} KB"
    elif bytes_ < 1073741824: return f"{bytes_/1048576:.1f} MB"
    return f"{bytes_/1073741824:.2f} GB"

def fmt_duration(sec: int) -> str:
    if sec < 60: return f"{sec}s"
    elif sec < 3600: return f"{sec//60}m {sec%60}s"
    return f"{sec//3600}h {(sec%3600)//60}m"

def fmt_uptime() -> str:
    delta = datetime.now() - bot_stats["start_time"]
    h, rem = divmod(int(delta.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m {s}s"

def is_youtube_url(url: str) -> bool:
    patterns = [r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/", r"(https?://)?(music\.youtube\.com)/"]
    return any(re.search(p, url) for p in patterns)

def is_playlist_url(url: str) -> bool:
    return "list=" in url or "/playlist" in url

def check_access(user_id: int) -> bool:
    if not RESTRICTED_MODE:
        return True
    return user_id in ALLOWED_USERS or user_id in ADMIN_IDS

# ─── YT-DLP Helpers (Improved for 2026) ─────────────────────────────────────
def get_ydl_opts_base() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "cookiefile": str(COOKIES_FILE) if COOKIES_FILE.exists() else None,
        "extractor_args": {"youtube": {"player_client": ["android", "web", "ios"]}},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "http_headers": {"Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.youtube.com/"},
        "socket_timeout": 30,
        "retries": 3,
    }
    if PROXY:
        opts["proxy"] = PROXY
    return opts

def get_video_info(url: str) -> Optional[dict]:
    opts = {**get_ydl_opts_base(), "skip_download": True, "extract_flat": False, "ignoreerrors": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error(f"Info error: {e}")
        # Fallback
        try:
            opts["extractor_args"] = {"youtube": {"player_client": ["ios", "android", "web"]}}
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as e2:
            logger.error(f"Fallback failed: {e2}")
            return None

def get_playlist_info(url: str) -> Optional[dict]:
    opts = {**get_ydl_opts_base(), "skip_download": True, "extract_flat": True, "ignoreerrors": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error(f"Playlist info error: {e}")
        return None

def get_available_formats(info: dict) -> list[dict]:
    formats = info.get("formats", [])
    seen = set()
    result = []
    for f in formats:
        if f.get("vcodec") != "none" and (height := f.get("height")) and height not in seen:
            seen.add(height)
            result.append({
                "label": f"{height}p",
                "height": height,
                "format_id": f.get("format_id"),
                "ext": f.get("ext", ""),
                "filesize": f.get("filesize") or f.get("filesize_approx"),
            })
    result.sort(key=lambda x: x["height"], reverse=True)
    return result[:6]

# ─── Keyboards ───────────────────────────────────────────────────────────────
def kb_main_menu(is_playlist: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"{E['audio']} Audio MP3", callback_data="dl_audio"),
         InlineKeyboardButton(f"{E['video']} Best Video", callback_data="dl_video_best")],
        [InlineKeyboardButton(f"{E['quality']} Choose Quality", callback_data="dl_quality")],
    ]
    if is_playlist:
        rows.append([
            InlineKeyboardButton(f"{E['list']} Playlist Audio", callback_data="pl_audio"),
            InlineKeyboardButton(f"{E['list']} Playlist Video", callback_data="pl_video"),
        ])
    rows.append([InlineKeyboardButton(f"{E['cross']} Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(rows)

def kb_quality(formats: list) -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(formats), 2):
        row = []
        for f in formats[i:i+2]:
            size_str = f" ({fmt_size(f['filesize'])})" if f.get("filesize") else ""
            row.append(InlineKeyboardButton(f"{E['quality']} {f['label']}{size_str}", callback_data=f"quality_{f['height']}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(f"{E['cross']} Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(rows)

def kb_playlist_options(count: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"{E['audio']} All as MP3 ({count})", callback_data="pl_audio"),
         InlineKeyboardButton(f"{E['video']} All as MP4 ({count})", callback_data="pl_video")],
        [InlineKeyboardButton(f"{E['cross']} Cancel", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(rows)

# ─── Progress Hook ───────────────────────────────────────────────────────────
def make_progress_hook(chat_id: int, msg_id: int, context: ContextTypes.DEFAULT_TYPE, title: str = ""):
    last_update = [0.0]
    def hook(d):
        nonlocal last_update
        if time.time() - last_update[0] < 3:
            return
        last_update[0] = time.time()

        if d["status"] == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0
            percent = (downloaded / total * 100) if total else 0
            bar = make_progress_bar(percent)

            text = (f"{E['dl']} <b>Downloading...</b>\n\n"
                    f"🎯 <b>{title[:40]}</b>\n\n"
                    f"<code>[{bar}] {percent:.1f}%</code>\n\n"
                    f"{E['size']} <b>Size:</b> {fmt_size(downloaded)}" + (f" / {fmt_size(total)}" if total else "") +
                    f"\n{E['rocket']} <b>Speed:</b> {fmt_size(int(speed))}/s\n"
                    f"{E['time']} <b>ETA:</b> {fmt_duration(int(eta))}")
            asyncio.create_task(_edit_message(context, chat_id, msg_id, text))

    return hook

async def _edit_message(context, chat_id, msg_id, text):
    try:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, parse_mode=ParseMode.HTML)
    except Exception:
        pass

# ─── Download Functions ─────────────────────────────────────────────────────
async def download_audio(url: str, chat_id: int, msg_id: int, context: ContextTypes.DEFAULT_TYPE, title: str = "") -> Optional[Path]:
    loop = asyncio.get_event_loop()
    out_tmpl = str(DOWNLOAD_DIR / f"{chat_id}_%(id)s.%(ext)s")
    opts = {
        **get_ydl_opts_base(),
        "format": "bestaudio/best",
        "outtmpl": out_tmpl,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
            {"key": "FFmpegMetadata"},
            {"key": "EmbedThumbnail"},
        ],
        "writethumbnail": True,
        "progress_hooks": [make_progress_hook(chat_id, msg_id, context, title)],
    }
    try:
        async with download_semaphore:
            info = await loop.run_in_executor(None, lambda: _run_download(url, opts))
            if not info:
                return None
            vid_id = info.get("id", "")
            for f in DOWNLOAD_DIR.glob(f"{chat_id}_{vid_id}*.mp3"):
                return f
            for f in sorted(DOWNLOAD_DIR.glob(f"{chat_id}_*.mp3"), key=lambda x: x.stat().st_mtime, reverse=True):
                return f
    except Exception as e:
        logger.error(f"Audio download error: {e}")
    return None

async def download_video(url: str, chat_id: int, msg_id: int, context: ContextTypes.DEFAULT_TYPE, title: str = "", height: int = 0) -> Optional[Path]:
    loop = asyncio.get_event_loop()
    fmt = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best" if height else "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
    out_tmpl = str(DOWNLOAD_DIR / f"{chat_id}_%(id)s.%(ext)s")
    opts = {
        **get_ydl_opts_base(),
        "format": fmt,
        "outtmpl": out_tmpl,
        "merge_output_format": "mp4",
        "postprocessors": [{"key": "FFmpegMetadata"}],
        "progress_hooks": [make_progress_hook(chat_id, msg_id, context, title)],
    }
    try:
        async with download_semaphore:
            info = await loop.run_in_executor(None, lambda: _run_download(url, opts))
            if not info:
                return None
            vid_id = info.get("id", "")
            for f in DOWNLOAD_DIR.glob(f"{chat_id}_{vid_id}*.mp4"):
                return f
            for f in sorted(DOWNLOAD_DIR.glob(f"{chat_id}_*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True):
                return f
    except Exception as e:
        logger.error(f"Video download error: {e}")
    return None

def _run_download(url: str, opts: dict) -> Optional[dict]:
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=True)
    except Exception as e:
        logger.error(f"yt-dlp error: {e}")
        return None

async def send_audio_file(update: Update, context: ContextTypes.DEFAULT_TYPE,
                          path: Path, info: dict, chat_id: int):
    file_size = path.stat().st_size
    if file_size > MAX_FILE_MB * 1024 * 1024:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{E['warn']} File is too large ({fmt_size(file_size)}) for Telegram. "
                 f"Max allowed: {MAX_FILE_MB}MB",
            parse_mode=ParseMode.HTML
        )
        return

    title    = info.get("title", "Unknown")
    artist   = info.get("uploader", "Unknown")
    duration = int(info.get("duration") or 0)

    caption = (
        f"{E['music']} <b>{title}</b>\n"
        f"👤 {artist}\n"
        f"{E['time']} {fmt_duration(duration)}\n"
        f"{E['disk']} {fmt_size(file_size)}"
    )

    # Find thumbnail
    thumb_file = None
    for ext in ["jpg", "jpeg", "png", "webp"]:
        for f in DOWNLOAD_DIR.glob(f"{chat_id}_*.{ext}"):
            thumb_file = f
            break

    try:
        with open(path, "rb") as audio_f:
            thumb_data = open(thumb_file, "rb") if thumb_file else None
            await context.bot.send_audio(
                chat_id=chat_id,
                audio=audio_f,
                caption=caption,
                parse_mode=ParseMode.HTML,
                title=title,
                performer=artist,
                duration=duration,
                thumbnail=thumb_data,
            )
            if thumb_data:
                thumb_data.close()
    except Exception as e:
        logger.error(f"Send audio error: {e}")
        raise

async def send_video_file(update: Update, context: ContextTypes.DEFAULT_TYPE,
                          path: Path, info: dict, chat_id: int):
    file_size = path.stat().st_size
    if file_size > MAX_FILE_MB * 1024 * 1024:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{E['warn']} File is too large ({fmt_size(file_size)}) for Telegram. "
                 f"Max allowed: {MAX_FILE_MB}MB",
            parse_mode=ParseMode.HTML
        )
        return

    title    = info.get("title", "Unknown")
    artist   = info.get("uploader", "Unknown")
    duration = int(info.get("duration") or 0)
    width    = info.get("width", 0)
    height   = info.get("height", 0)

    caption = (
        f"{E['video']} <b>{title}</b>\n"
        f"👤 {artist}\n"
        f"{E['time']} {fmt_duration(duration)}\n"
        f"{E['quality']} {width}×{height}\n"
        f"{E['disk']} {fmt_size(file_size)}"
    )

    try:
        with open(path, "rb") as video_f:
            await context.bot.send_video(
                chat_id=chat_id,
                video=video_f,
                caption=caption,
                parse_mode=ParseMode.HTML,
                duration=duration,
                width=width or None,
                height=height or None,
                supports_streaming=True,
            )
    except Exception as e:
        logger.error(f"Send video error: {e}")
        raise

def cleanup_files(chat_id: int):
    if not AUTO_DELETE:
        return
    for f in DOWNLOAD_DIR.glob(f"{chat_id}_*"):
        try:
            f.unlink()
        except Exception:
            pass

# ─── Command Handlers ─────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not check_access(user.id):
        await update.message.reply_text(f"{E['cross']} You are not authorized to use this bot.")
        return

    text = (
        f"{E['wave']} <b>Welcome, {user.first_name}!</b>\n\n"
        f"{E['rocket']} <b>YT-DLP Bot</b> — your all-in-one YouTube downloader\n\n"
        f"<b>What I can do:</b>\n"
        f"{E['audio']} Download <b>audio</b> as high-quality MP3\n"
        f"{E['video']} Download <b>videos</b> in up to 1080p\n"
        f"{E['list']} Handle full <b>playlists</b>\n"
        f"{E['quality']} Choose your preferred <b>quality</b>\n"
        f"{E['star']} Embed <b>thumbnails</b> & metadata\n\n"
        f"<b>Just send me a YouTube link!</b>\n\n"
        f"📋 <b>Commands:</b>\n"
        f"/start — this message\n"
        f"/help — detailed help\n"
        f"/stats — bot statistics\n"
        f"/cancel — cancel your downloads\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"{E['info']} <b>How to use this bot:</b>\n\n"
        f"<b>1.</b> Send any YouTube URL (video or playlist)\n"
        f"<b>2.</b> Choose your download type:\n"
        f"   {E['audio']} <b>Audio MP3</b> — best quality audio, 192kbps\n"
        f"   {E['video']} <b>Best Video</b> — best available quality\n"
        f"   {E['quality']} <b>Choose Quality</b> — pick specific resolution\n"
        f"   {E['list']} <b>Playlist</b> — download entire playlist\n\n"
        f"<b>Supported URLs:</b>\n"
        f"• youtube.com/watch?v=...\n"
        f"• youtu.be/...\n"
        f"• youtube.com/playlist?list=...\n"
        f"• music.youtube.com/...\n\n"
        f"{E['warn']} <b>Limits:</b> Max file size {MAX_FILE_MB}MB\n"
        f"{E['gear']} Max {MAX_PER_USER} concurrent downloads per user\n\n"
        f"{E['heart']} Enjoy your downloads!"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_admin = user.id in ADMIN_IDS

    text = (
        f"{E['chart']} <b>Bot Statistics</b>\n\n"
        f"{E['rocket']} <b>Total Downloads:</b> {bot_stats['total_downloads']}\n"
        f"{E['audio']} <b>Audio Downloads:</b> {bot_stats['total_audio']}\n"
        f"{E['video']} <b>Video Downloads:</b> {bot_stats['total_video']}\n"
        f"{E['list']} <b>Playlist Jobs:</b> {bot_stats['total_playlist']}\n"
        f"{E['clock']} <b>Uptime:</b> {fmt_uptime()}\n"
    )
    if is_admin:
        active = len(active_downloads)
        text += (
            f"\n{E['crown']} <b>Admin Info:</b>\n"
            f"• Active downloads: {active}\n"
            f"• Downloads dir: {DOWNLOAD_DIR}\n"
            f"• Cookies: {'✅ Loaded' if COOKIES_FILE.exists() else '❌ Missing'}\n"
        )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in active_downloads:
        active_downloads[chat_id]["cancelled"] = True
        await update.message.reply_text(
            f"{E['cancel']} Cancellation requested. "
            "Current download will stop after the current file.",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            f"{E['info']} No active downloads to cancel.",
            parse_mode=ParseMode.HTML
        )

# ─── URL Handler ─────────────────────────────────────────────────────────────
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    chat_id = update.effective_chat.id
    url     = update.message.text.strip()

    if not check_access(user.id):
        await update.message.reply_text(f"{E['cross']} Not authorized.")
        return

    if not is_youtube_url(url):
        return

    if user_download_count[user.id] >= MAX_PER_USER:
        await update.message.reply_text(
            f"{E['warn']} You already have {MAX_PER_USER} active downloads. "
            "Please wait or use /cancel.",
            parse_mode=ParseMode.HTML
        )
        return

    # Store URL in context for callback use
    context.user_data["url"] = url

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    # Fetch info
    status_msg = await update.message.reply_text(
        f"{E['wait']} <b>Fetching video information...</b>",
        parse_mode=ParseMode.HTML
    )

    loop = asyncio.get_event_loop()
    is_playlist = is_playlist_url(url)

    try:
        if is_playlist:
            info = await loop.run_in_executor(None, lambda: get_playlist_info(url))
        else:
            info = await loop.run_in_executor(None, lambda: get_video_info(url))
    except Exception as e:
        await status_msg.edit_text(f"{E['cross']} Error fetching info: {e}")
        return

    if not info:
        await status_msg.edit_text(
            f"{E['cross']} <b>Could not fetch video info.</b>\n\n"
            "Make sure the URL is valid and accessible.",
            parse_mode=ParseMode.HTML
        )
        return

    context.user_data["info"] = info

    if is_playlist:
        entries = info.get("entries", [])
        count   = len(entries)
        p_title = info.get("title", "Unknown Playlist")

        text = (
            f"{E['list']} <b>Playlist Detected!</b>\n\n"
            f"📌 <b>{p_title}</b>\n"
            f"🎞️ <b>{count} videos</b>\n\n"
            f"Choose download format:"
        )
        await status_msg.edit_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=kb_playlist_options(count)
        )
    else:
        title    = info.get("title", "Unknown")
        channel  = info.get("uploader", "Unknown")
        duration = int(info.get("duration") or 0)
        views    = info.get("view_count", 0)
        thumb    = info.get("thumbnail", "")

        # Get available formats for quality selector
        avail_formats = get_available_formats(info)
        context.user_data["formats"] = avail_formats

        text = (
            f"{E['video']} <b>Video Found!</b>\n\n"
            f"🎯 <b>{title}</b>\n"
            f"👤 {channel}\n"
            f"{E['time']} {fmt_duration(duration)}\n"
            f"👁 {views:,} views\n\n"
            f"Choose download format:"
        )
        await status_msg.edit_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=kb_main_menu(is_playlist=False)
        )

# ─── Callback Handler ─────────────────────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    chat_id = query.message.chat_id
    data    = query.data
    user    = query.from_user

    await query.answer()

    if data == "cancel":
        await query.message.edit_text(f"{E['cancel']} Cancelled.")
        context.user_data.clear()
        return

    if data == "dl_quality":
        formats = context.user_data.get("formats", [])
        if not formats:
            await query.message.edit_text(f"{E['cross']} No quality options found.")
            return
        await query.message.edit_text(
            f"{E['quality']} <b>Select Video Quality:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_quality(formats)
        )
        return

    url  = context.user_data.get("url")
    info = context.user_data.get("info")

    if not url:
        await query.message.edit_text(f"{E['cross']} Session expired. Please resend the URL.")
        return

    # Determine action
    if data == "dl_audio":
        await _do_audio(query, context, chat_id, url, info, user)
    elif data == "dl_video_best":
        await _do_video(query, context, chat_id, url, info, user, height=0)
    elif data.startswith("quality_"):
        height = int(data.split("_")[1])
        await _do_video(query, context, chat_id, url, info, user, height=height)
    elif data == "pl_audio":
        await _do_playlist(query, context, chat_id, url, info, user, mode="audio")
    elif data == "pl_video":
        await _do_playlist(query, context, chat_id, url, info, user, mode="video")

async def _do_audio(query, context, chat_id, url, info, user):
    title = info.get("title", "Unknown") if info else "Unknown"
    user_download_count[user.id] += 1
    active_downloads[chat_id] = {"cancelled": False, "url": url}
    bot_stats["total_downloads"] += 1
    bot_stats["total_audio"] += 1

    await query.message.edit_text(
        f"{E['wait']} <b>Preparing audio download...</b>\n\n"
        f"🎯 <b>{title[:50]}</b>",
        parse_mode=ParseMode.HTML
    )

    try:
        path = await download_audio(url, chat_id, query.message.message_id, context, title)
        if not path or not path.exists():
            await query.message.edit_text(f"{E['cross']} Download failed. Please try again.")
            return

        await query.message.edit_text(
            f"{E['check']} <b>Download complete! Uploading...</b>",
            parse_mode=ParseMode.HTML
        )

        real_info = info or {}
        await send_audio_file(query, context, path, real_info, chat_id)
        await query.message.delete()

    except Exception as e:
        logger.error(f"Audio pipeline error: {e}")
        await query.message.edit_text(f"{E['cross']} Error: {e}")
    finally:
        user_download_count[user.id] = max(0, user_download_count[user.id] - 1)
        active_downloads.pop(chat_id, None)
        cleanup_files(chat_id)

async def _do_video(query, context, chat_id, url, info, user, height: int = 0):
    title = info.get("title", "Unknown") if info else "Unknown"
    label = f"{height}p" if height else "Best"
    user_download_count[user.id] += 1
    active_downloads[chat_id] = {"cancelled": False, "url": url}
    bot_stats["total_downloads"] += 1
    bot_stats["total_video"] += 1

    await query.message.edit_text(
        f"{E['wait']} <b>Preparing {label} video download...</b>\n\n"
        f"🎯 <b>{title[:50]}</b>",
        parse_mode=ParseMode.HTML
    )

    try:
        path = await download_video(url, chat_id, query.message.message_id, context, title, height)
        if not path or not path.exists():
            await query.message.edit_text(f"{E['cross']} Download failed. Please try again.")
            return

        await query.message.edit_text(
            f"{E['check']} <b>Download complete! Uploading...</b>",
            parse_mode=ParseMode.HTML
        )

        real_info = info or {}
        await send_video_file(query, context, path, real_info, chat_id)
        await query.message.delete()

    except Exception as e:
        logger.error(f"Video pipeline error: {e}")
        await query.message.edit_text(f"{E['cross']} Error: {e}")
    finally:
        user_download_count[user.id] = max(0, user_download_count[user.id] - 1)
        active_downloads.pop(chat_id, None)
        cleanup_files(chat_id)

async def _do_playlist(query, context, chat_id, url, info, user, mode: str = "audio"):
    entries = info.get("entries", []) if info else []
    p_title = info.get("title", "Playlist") if info else "Playlist"
    total   = len(entries)
    mode_label = "audio" if mode == "audio" else "video"

    user_download_count[user.id] += 1
    active_downloads[chat_id] = {"cancelled": False, "url": url}
    bot_stats["total_downloads"] += 1
    bot_stats["total_playlist"] += 1

    await query.message.edit_text(
        f"{E['list']} <b>Starting playlist download...</b>\n\n"
        f"📌 <b>{p_title}</b>\n"
        f"🎞️ {total} {mode_label} files\n\n"
        f"{E['wait']} Processing...",
        parse_mode=ParseMode.HTML
    )

    success_count = 0
    fail_count    = 0

    try:
        for i, entry in enumerate(entries, 1):
            if active_downloads.get(chat_id, {}).get("cancelled"):
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"{E['cancel']} Playlist download cancelled. "
                         f"Downloaded {success_count}/{total}.",
                    parse_mode=ParseMode.HTML
                )
                break

            entry_url   = entry.get("url") or entry.get("webpage_url")
            entry_title = entry.get("title", f"Track {i}")

            if not entry_url:
                fail_count += 1
                continue

            # Update progress message
            bar = make_progress_bar(i / total * 100)
            try:
                await query.message.edit_text(
                    f"{E['list']} <b>Playlist: {p_title}</b>\n\n"
                    f"<code>[{bar}] {i}/{total}</code>\n\n"
                    f"{E['dl']} <b>Now:</b> {entry_title[:40]}\n"
                    f"{E['check']} Done: {success_count}  {E['cross']} Failed: {fail_count}",
                    parse_mode=ParseMode.HTML
                )
            except TelegramError:
                pass

            try:
                # Get full info for this entry
                entry_info = await asyncio.get_event_loop().run_in_executor(
                    None, lambda u=entry_url: get_video_info(u)
                )
                if not entry_info:
                    fail_count += 1
                    continue

                if mode == "audio":
                    path = await download_audio(
                        entry_url, chat_id,
                        query.message.message_id, context, entry_title
                    )
                    if path and path.exists():
                        await send_audio_file(query, context, path, entry_info, chat_id)
                        success_count += 1
                    else:
                        fail_count += 1
                else:
                    path = await download_video(
                        entry_url, chat_id,
                        query.message.message_id, context, entry_title
                    )
                    if path and path.exists():
                        await send_video_file(query, context, path, entry_info, chat_id)
                        success_count += 1
                    else:
                        fail_count += 1

            except Exception as e:
                logger.error(f"Playlist entry {i} error: {e}")
                fail_count += 1

            cleanup_files(chat_id)
            await asyncio.sleep(1)  # Small delay between uploads

        # Final summary
        await query.message.edit_text(
            f"{E['check']} <b>Playlist complete!</b>\n\n"
            f"📌 <b>{p_title}</b>\n\n"
            f"{E['check']} Successfully sent: <b>{success_count}</b>\n"
            f"{E['cross']} Failed: <b>{fail_count}</b>\n"
            f"🎞️ Total: <b>{total}</b>",
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Playlist error: {e}")
        await query.message.edit_text(
            f"{E['cross']} Playlist download failed: {e}",
            parse_mode=ParseMode.HTML
        )
    finally:
        user_download_count[user.id] = max(0, user_download_count[user.id] - 1)
        active_downloads.pop(chat_id, None)
        cleanup_files(chat_id)

# ─── Unknown messages ─────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text:
        text = update.message.text.strip()
        if text.startswith("http"):
            if not is_youtube_url(text):
                await update.message.reply_text(
                    f"{E['warn']} Only YouTube URLs are supported.\n"
                    "Please send a valid youtube.com or youtu.be link.",
                    parse_mode=ParseMode.HTML
                )
            # else handled by handle_url
        else:
            await update.message.reply_text(
                f"{E['info']} Send me a YouTube URL to get started!\n"
                f"Use /help for instructions.",
                parse_mode=ParseMode.HTML
            )

# ─── Error Handler ────────────────────────────────────────────────────────────
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                f"{E['cross']} An unexpected error occurred. Please try again.",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

# ─── Main ─────────────────────────────────────────────────────────────────────
async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start",  "Welcome message"),
        BotCommand("help",   "How to use the bot"),
        BotCommand("stats",  "Download statistics"),
        BotCommand("cancel", "Cancel active download"),
    ])
    logger.info("Bot commands set.")

def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌  ERROR: Set BOT_TOKEN in your .env file!")
        sys.exit(1)

    if not COOKIES_FILE.exists():
        logger.warning(f"Cookies file not found: {COOKIES_FILE}")
    else:
        logger.info(f"✅ Cookies loaded from {COOKIES_FILE}")

    logger.info("🚀 Starting YT-DLP Telegram Bot...")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Handlers
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("stats",  cmd_stats))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"https?://") & ~filters.COMMAND,
        handle_url
    ))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_error_handler(error_handler)

    logger.info("✅ Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
