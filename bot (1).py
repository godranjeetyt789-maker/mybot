"""
╔══════════════════════════════════════════════════════════╗
║        FORCE JOIN TELEGRAM BOT — SINGLE FILE             ║
║  Set karo: BOT_TOKEN, ADMIN_IDS env variables            ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import sqlite3
import threading
import logging
from datetime import date
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telegram.constants import ParseMode

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "bot_data.db")

# ═══════════════════════════════════════════════════════════
#  KEEP-ALIVE  (Render free tier ke liye)
# ═══════════════════════════════════════════════════════════

class _PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")
    def log_message(self, *a): pass

def start_keep_alive(port: int = 8080):
    server = HTTPServer(("0.0.0.0", port), _PingHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info(f"Keep-alive server port {port} pe chal raha hai")

# ═══════════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════════

def _conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id      INTEGER PRIMARY KEY,
                username     TEXT    DEFAULT '',
                first_name   TEXT    DEFAULT '',
                joined_date  TEXT    DEFAULT '',
                is_blocked   INTEGER DEFAULT 0,
                last_bot_msg INTEGER DEFAULT 0
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            )
        """)
        defaults = {
            "channel_id":      "",
            "channel_link":    "https://t.me/yourchannel",
            "channel_name":    "Our Channel",
            "channel_preview": "📢 <b>{channel_name}</b>\n\n🎯 Latest updates milte hain yahan.\n👇 Channel visit karo:",
            "voice_file_id":   "",
            "deposit_link":    "",
            "deposit_text":    "💰 <b>Deposit Karo</b>\n\nNiche link pe click karo:",
            "welcome_text":    "👋 <b>Namaste {name}!</b>\n\n🔒 Bot use karne ke liye pehle hamara <b>Channel Join</b> karo.\n\n👇 Niche button dabao:",
        }
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (k, v))
        c.commit()

# — users —
def db_add_user(user_id, username, first_name):
    with _conn() as c:
        c.execute("""
            INSERT INTO users (user_id, username, first_name, joined_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username, first_name=excluded.first_name
        """, (user_id, username, first_name, str(date.today())))
        c.commit()

def db_all_users():
    with _conn() as c:
        return [r[0] for r in c.execute("SELECT user_id FROM users WHERE is_blocked=0").fetchall()]

def db_is_blocked(uid):
    with _conn() as c:
        r = c.execute("SELECT is_blocked FROM users WHERE user_id=?", (uid,)).fetchone()
    return bool(r and r[0])

def db_block(uid):
    with _conn() as c:
        c.execute("UPDATE users SET is_blocked=1 WHERE user_id=?", (uid,)); c.commit()

def db_unblock(uid):
    with _conn() as c:
        c.execute("UPDATE users SET is_blocked=0 WHERE user_id=?", (uid,)); c.commit()

def db_set_msg(uid, mid):
    with _conn() as c:
        c.execute("UPDATE users SET last_bot_msg=? WHERE user_id=?", (mid, uid)); c.commit()

def db_get_msg(uid):
    with _conn() as c:
        r = c.execute("SELECT last_bot_msg FROM users WHERE user_id=?", (uid,)).fetchone()
    return r[0] if r and r[0] else None

def db_stats():
    with _conn() as c:
        total   = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        active  = c.execute("SELECT COUNT(*) FROM users WHERE is_blocked=0").fetchone()[0]
        blocked = c.execute("SELECT COUNT(*) FROM users WHERE is_blocked=1").fetchone()[0]
        today   = c.execute("SELECT COUNT(*) FROM users WHERE joined_date=?", (str(date.today()),)).fetchone()[0]
    return {"total": total, "active": active, "blocked": blocked, "today": today}

# — config —
def cfg_get():
    with _conn() as c:
        rows = c.execute("SELECT key, value FROM config").fetchall()
    return dict(rows)

def cfg_set(key, value):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value)); c.commit()

# ═══════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════

def admin_ids():
    return [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

async def is_member(bot, uid, channel_id):
    try:
        m = await bot.get_chat_member(channel_id, uid)
        return m.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except Exception:
        return False

def kb_not_joined(link):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Channel Join Karo", url=link)],
        [InlineKeyboardButton("✅ Joined – Verify Karo", callback_data="verify_join")],
    ])

def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Deposit", callback_data="deposit")],
        [InlineKeyboardButton("📢 Channel", callback_data="open_channel")],
    ])

def kb_admin():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Channel Settings",  callback_data="admin_channel_menu")],
        [InlineKeyboardButton("🎙️ Voice Message",     callback_data="admin_voice_menu")],
        [InlineKeyboardButton("💰 Deposit Link",      callback_data="admin_deposit_menu")],
        [InlineKeyboardButton("📝 Welcome Text",      callback_data="admin_welcome_menu")],
        [InlineKeyboardButton("📨 Broadcast",         callback_data="admin_broadcast_menu")],
        [InlineKeyboardButton("👥 Users & Stats",     callback_data="admin_stats")],
        [InlineKeyboardButton("🚫 Block User",        callback_data="admin_block_menu")],
        [InlineKeyboardButton("✅ Unblock User",      callback_data="admin_unblock_menu")],
    ])

def kb_back(target="admin_panel"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=target)]])

# ═══════════════════════════════════════════════════════════
#  JOINED CONTENT  (voice + channel card)
# ═══════════════════════════════════════════════════════════

async def send_joined_content(send_fn, chat_id, user, context, cfg):
    voice_id = cfg.get("voice_file_id", "")
    ch_link  = cfg.get("channel_link", "https://t.me/yourchannel")
    ch_name  = cfg.get("channel_name", "Our Channel")
    preview  = cfg.get("channel_preview",
        "📢 <b>{channel_name}</b>\n\n🎯 Latest updates milte hain.\n👇 Channel visit karo:")

    # 1️⃣ Voice
    if voice_id:
        try:
            await context.bot.send_voice(
                chat_id=chat_id, voice=voice_id,
                caption=f"🎙️ Welcome {user.first_name}! Suniye hamara message.",
            )
        except Exception as e:
            logger.warning(f"Voice send failed: {e}")

    # 2️⃣ Channel card
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📢 {ch_name} Open Karo", url=ch_link)],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
    ])
    text = preview.format(channel_name=ch_name, name=user.first_name)
    sent = await send_fn(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    db_set_msg(user.id, sent.message_id)

# ═══════════════════════════════════════════════════════════
#  /start
# ═══════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_add_user(user.id, user.username or "", user.first_name or "")

    # Delete previous bot message
    prev = db_get_msg(user.id)
    if prev:
        try:
            await context.bot.delete_message(update.effective_chat.id, prev)
        except Exception:
            pass

    cfg = cfg_get()
    ch_id   = cfg.get("channel_id", "")
    ch_link = cfg.get("channel_link", "https://t.me/yourchannel")

    if not ch_id:
        sent = await update.message.reply_text("⚠️ Admin ne channel set nahi kiya. Baad mein try karo.")
        db_set_msg(user.id, sent.message_id)
        return

    if db_is_blocked(user.id):
        await update.message.reply_text("🚫 Aap block hain. Admin se contact karo.")
        return

    joined = await is_member(context.bot, user.id, ch_id)
    if not joined:
        text = cfg.get("welcome_text", "👋 <b>Namaste {name}!</b>\n\n🔒 Pehle channel join karo.").format(name=user.first_name)
        sent = await update.message.reply_text(text, reply_markup=kb_not_joined(ch_link), parse_mode=ParseMode.HTML)
        db_set_msg(user.id, sent.message_id)
    else:
        await send_joined_content(update.message.reply_text, update.effective_chat.id, user, context, cfg)

# ═══════════════════════════════════════════════════════════
#  /admin
# ═══════════════════════════════════════════════════════════

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admin_ids():
        return
    await update.message.reply_text(
        "👑 <b>Admin Panel</b>\n\nKya change karna hai?",
        reply_markup=kb_admin(), parse_mode=ParseMode.HTML,
    )

# ═══════════════════════════════════════════════════════════
#  CALLBACK HANDLER
# ═══════════════════════════════════════════════════════════

async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    user = q.from_user
    data = q.data
    cfg  = cfg_get()
    await q.answer()

    # ── VERIFY JOIN ──────────────────────────────────────
    if data == "verify_join":
        ch_id   = cfg.get("channel_id", "")
        ch_link = cfg.get("channel_link", "https://t.me/yourchannel")
        if not ch_id:
            await q.answer("⚠️ Channel set nahi hai.", show_alert=True); return
        if db_is_blocked(user.id):
            await q.answer("🚫 Aap block hain.", show_alert=True); return
        if not await is_member(context.bot, user.id, ch_id):
            await q.answer("❌ Abhi join nahi kiya! Pehle join karo.", show_alert=True); return
        try: await q.message.delete()
        except Exception: pass
        await send_joined_content(
            lambda *a, **kw: context.bot.send_message(q.message.chat_id, *a, **kw),
            q.message.chat_id, user, context, cfg,
        )

    # ── MAIN MENU ────────────────────────────────────────
    elif data == "main_menu":
        await q.edit_message_text(
            f"🏠 <b>Main Menu</b>\n\nKya karna chahte ho, {user.first_name}?",
            reply_markup=kb_main(), parse_mode=ParseMode.HTML,
        )

    # ── DEPOSIT ──────────────────────────────────────────
    elif data == "deposit":
        link = cfg.get("deposit_link", "")
        if not link:
            await q.answer("⚠️ Admin ne deposit link set nahi kiya.", show_alert=True); return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Deposit Link", url=link)],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
        ])
        await q.edit_message_text(
            cfg.get("deposit_text", "💰 <b>Deposit Karo</b>"),
            reply_markup=kb, parse_mode=ParseMode.HTML,
        )

    # ── OPEN CHANNEL ─────────────────────────────────────
    elif data == "open_channel":
        ch_link = cfg.get("channel_link", "https://t.me/yourchannel")
        ch_name = cfg.get("channel_name", "Our Channel")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📢 {ch_name}", url=ch_link)],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
        ])
        await q.edit_message_text(
            f"📢 <b>{ch_name}</b>\n\nYahan click karo channel open karne ke liye:",
            reply_markup=kb, parse_mode=ParseMode.HTML,
        )

    # ══════════════════════════════════════════════════════
    #  ADMIN CALLBACKS
    # ══════════════════════════════════════════════════════
    elif data.startswith("admin_"):
        if user.id not in admin_ids():
            await q.answer("🚫 Admin only!", show_alert=True); return

        # ── MAIN PANEL ───────────────────────────────────
        if data == "admin_panel":
            await q.edit_message_text(
                "👑 <b>Admin Panel</b>\n\nKya change karna hai?",
                reply_markup=kb_admin(), parse_mode=ParseMode.HTML,
            )

        # ── CHANNEL ──────────────────────────────────────
        elif data == "admin_channel_menu":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🆔 Channel ID",   callback_data="admin_set_channel_id")],
                [InlineKeyboardButton("🔗 Channel Link", callback_data="admin_set_channel_link")],
                [InlineKeyboardButton("✏️ Channel Name", callback_data="admin_set_channel_name")],
                [InlineKeyboardButton("🔙 Back",          callback_data="admin_panel")],
            ])
            await q.edit_message_text(
                f"📢 <b>Channel Settings</b>\n\n"
                f"🆔 ID: <code>{cfg.get('channel_id','Not set')}</code>\n"
                f"🔗 Link: {cfg.get('channel_link','Not set')}\n"
                f"📛 Name: {cfg.get('channel_name','Not set')}",
                reply_markup=kb, parse_mode=ParseMode.HTML,
            )

        elif data == "admin_set_channel_id":
            context.user_data["awaiting"] = "channel_id"
            await q.edit_message_text(
                "📢 Channel ID bhejo (e.g. <code>-1001234567890</code>)\nBot ko admin banana na bhulo!",
                reply_markup=kb_back(), parse_mode=ParseMode.HTML,
            )

        elif data == "admin_set_channel_link":
            context.user_data["awaiting"] = "channel_link"
            await q.edit_message_text("🔗 Channel link bhejo:", reply_markup=kb_back(), parse_mode=ParseMode.HTML)

        elif data == "admin_set_channel_name":
            context.user_data["awaiting"] = "channel_name"
            await q.edit_message_text("✏️ Channel naam bhejo:", reply_markup=kb_back(), parse_mode=ParseMode.HTML)

        # ── VOICE ────────────────────────────────────────
        elif data == "admin_voice_menu":
            status = "✅ Set hai" if cfg.get("voice_file_id") else "❌ Set nahi"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎙️ Voice Upload", callback_data="admin_set_voice")],
                [InlineKeyboardButton("🗑️ Voice Delete",  callback_data="admin_del_voice")],
                [InlineKeyboardButton("🔙 Back",           callback_data="admin_panel")],
            ])
            await q.edit_message_text(
                f"🎙️ <b>Voice Message</b>\n\nStatus: {status}",
                reply_markup=kb, parse_mode=ParseMode.HTML,
            )

        elif data == "admin_set_voice":
            context.user_data["awaiting"] = "voice"
            await q.edit_message_text("🎙️ Voice note bhejo:", reply_markup=kb_back(), parse_mode=ParseMode.HTML)

        elif data == "admin_del_voice":
            cfg_set("voice_file_id", "")
            await q.answer("🗑️ Voice delete ho gaya!", show_alert=True)
            await q.edit_message_text("👑 <b>Admin Panel</b>", reply_markup=kb_admin(), parse_mode=ParseMode.HTML)

        # ── DEPOSIT ──────────────────────────────────────
        elif data == "admin_deposit_menu":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Link Set Karo", callback_data="admin_set_deposit_link")],
                [InlineKeyboardButton("📝 Text Set Karo", callback_data="admin_set_deposit_text")],
                [InlineKeyboardButton("🔙 Back",           callback_data="admin_panel")],
            ])
            await q.edit_message_text(
                f"💰 <b>Deposit Settings</b>\n\n🔗 Link: {cfg.get('deposit_link','Not set')}",
                reply_markup=kb, parse_mode=ParseMode.HTML,
            )

        elif data == "admin_set_deposit_link":
            context.user_data["awaiting"] = "deposit_link"
            await q.edit_message_text("💰 Deposit link bhejo:", reply_markup=kb_back(), parse_mode=ParseMode.HTML)

        elif data == "admin_set_deposit_text":
            context.user_data["awaiting"] = "deposit_text"
            await q.edit_message_text("📝 Deposit page text bhejo (HTML allowed):", reply_markup=kb_back(), parse_mode=ParseMode.HTML)

        # ── WELCOME TEXT ─────────────────────────────────
        elif data == "admin_welcome_menu":
            context.user_data["awaiting"] = "welcome_text"
            await q.edit_message_text(
                "📝 Welcome text bhejo (HTML allowed).\n<code>{name}</code> = user ka naam",
                reply_markup=kb_back(), parse_mode=ParseMode.HTML,
            )

        # ── STATS ────────────────────────────────────────
        elif data == "admin_stats":
            s = db_stats()
            await q.edit_message_text(
                f"📊 <b>Bot Statistics</b>\n\n"
                f"👥 Total: <b>{s['total']}</b>\n"
                f"🟢 Active: <b>{s['active']}</b>\n"
                f"🚫 Blocked: <b>{s['blocked']}</b>\n"
                f"📅 Today: <b>{s['today']}</b>",
                reply_markup=kb_back(), parse_mode=ParseMode.HTML,
            )

        # ── BROADCAST ────────────────────────────────────
        elif data == "admin_broadcast_menu":
            context.user_data["awaiting"] = "broadcast"
            await q.edit_message_text(
                "📨 <b>Broadcast</b>\n\nJo message bhejni hai woh type karo:",
                reply_markup=kb_back(), parse_mode=ParseMode.HTML,
            )

        # ── BLOCK / UNBLOCK ──────────────────────────────
        elif data == "admin_block_menu":
            context.user_data["awaiting"] = "block_user"
            await q.edit_message_text("🚫 Block karne ke liye User ID bhejo:", reply_markup=kb_back(), parse_mode=ParseMode.HTML)

        elif data == "admin_unblock_menu":
            context.user_data["awaiting"] = "unblock_user"
            await q.edit_message_text("✅ Unblock karne ke liye User ID bhejo:", reply_markup=kb_back(), parse_mode=ParseMode.HTML)

# ═══════════════════════════════════════════════════════════
#  MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════

async def msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    awaiting = context.user_data.get("awaiting", "")

    if db_is_blocked(user.id) and user.id not in admin_ids():
        await update.message.reply_text("🚫 Aap block hain. Admin se contact karo.")
        return

    if user.id in admin_ids() and awaiting:
        context.user_data.pop("awaiting", None)
        msg = update.message
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]])

        # Voice upload
        if awaiting == "voice":
            if msg.voice:
                cfg_set("voice_file_id", msg.voice.file_id)
                await msg.reply_text("✅ Voice message save ho gaya!", reply_markup=back_kb)
            else:
                await msg.reply_text("❌ Voice note bhejo, text nahi!")
            return

        # Broadcast
        if awaiting == "broadcast":
            users   = db_all_users()
            ok = fail = 0
            sm = await msg.reply_text("📨 Broadcast chal raha hai...")
            for uid in users:
                try:
                    await context.bot.send_message(uid, msg.text or msg.caption or "", parse_mode=ParseMode.HTML)
                    ok += 1
                except Exception:
                    fail += 1
            await sm.edit_text(
                f"📨 <b>Broadcast Complete!</b>\n\n✅ Sent: {ok}\n❌ Failed: {fail}",
                parse_mode=ParseMode.HTML, reply_markup=back_kb,
            )
            return

        # Block / Unblock
        if awaiting in ("block_user", "unblock_user"):
            try:
                uid = int(msg.text.strip())
                if awaiting == "block_user":
                    db_block(uid)
                    await msg.reply_text(f"🚫 User {uid} block ho gaya!", reply_markup=back_kb)
                else:
                    db_unblock(uid)
                    await msg.reply_text(f"✅ User {uid} unblock ho gaya!", reply_markup=back_kb)
            except ValueError:
                await msg.reply_text("❌ Valid User ID dalo!")
            return

        # Text config keys
        key_map = {
            "channel_id":   "channel_id",
            "channel_link": "channel_link",
            "channel_name": "channel_name",
            "deposit_link": "deposit_link",
            "deposit_text": "deposit_text",
            "welcome_text": "welcome_text",
        }
        if awaiting in key_map:
            cfg_set(key_map[awaiting], msg.text.strip())
            label = awaiting.replace("_", " ").title()
            await msg.reply_text(f"✅ <b>{label}</b> update ho gaya!", parse_mode=ParseMode.HTML, reply_markup=back_kb)

# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════

def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN environment variable set nahi hai!")

    init_db()

    port = int(os.getenv("PORT", 8080))
    start_keep_alive(port)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CallbackQueryHandler(cb_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, msg_handler))

    logger.info("✅ Bot chal raha hai...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
