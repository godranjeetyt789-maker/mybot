"""
╔══════════════════════════════════════════════════════════╗
║        FORCE JOIN TELEGRAM BOT — SINGLE FILE             ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import asyncio
import sqlite3
import threading
import logging
import json
from datetime import date
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telegram.constants import ParseMode

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "bot_data.db")

# ═══════════════════════════════════════════════════════════
#  KEEP-ALIVE
# ═══════════════════════════════════════════════════════════

class _PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b"Bot is alive!")
    def log_message(self, *a): pass

def start_keep_alive(port=10000):
    server = HTTPServer(("0.0.0.0", port), _PingHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info(f"Keep-alive port {port} pe chal raha hai")

# ═══════════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════════

def _conn(): return sqlite3.connect(DB_PATH)

def init_db():
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT DEFAULT '',
            first_name TEXT DEFAULT '', joined_date TEXT DEFAULT '',
            is_blocked INTEGER DEFAULT 0, last_bot_msg INTEGER DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY, value TEXT DEFAULT '')""")
        defaults = {
            "voice_file_id": "",
            "deposit_link":  "",
            "deposit_text":  "💰 <b>Deposit Karo</b>\n\nNiche link pe click karo:",
            "welcome_text":  "👋 <b>Namaste {name}!</b>\n\n🔒 Bot use karne ke liye pehle <b>Saare Channels Join</b> karo.\n\n👇 Niche join karo:",
            "joined_text":   "⚠️ Deposit Milega Play on\nSound 🔊 👆👆.",
            "channels":      "[]",
            "admin_ids":     "",
        }
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO config (key,value) VALUES (?,?)", (k, v))
        c.commit()

def db_add_user(uid, uname, fname):
    with _conn() as c:
        c.execute("""INSERT INTO users (user_id,username,first_name,joined_date)
            VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username, first_name=excluded.first_name""",
            (uid, uname, fname, str(date.today()))); c.commit()

def db_all_users():
    with _conn() as c:
        return [r[0] for r in c.execute("SELECT user_id FROM users WHERE is_blocked=0").fetchall()]

def db_is_blocked(uid):
    with _conn() as c:
        r = c.execute("SELECT is_blocked FROM users WHERE user_id=?", (uid,)).fetchone()
    return bool(r and r[0])

def db_block(uid):
    with _conn() as c: c.execute("UPDATE users SET is_blocked=1 WHERE user_id=?", (uid,)); c.commit()

def db_unblock(uid):
    with _conn() as c: c.execute("UPDATE users SET is_blocked=0 WHERE user_id=?", (uid,)); c.commit()

def db_set_msg(uid, mid):
    with _conn() as c: c.execute("UPDATE users SET last_bot_msg=? WHERE user_id=?", (mid, uid)); c.commit()

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
    return {"total":total,"active":active,"blocked":blocked,"today":today}

# ═══════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════

def cfg_get():
    with _conn() as c:
        rows = c.execute("SELECT key,value FROM config").fetchall()
    return dict(rows)

def cfg_set(key, value):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO config (key,value) VALUES (?,?)", (key, value)); c.commit()

def get_channels():
    cfg = cfg_get()
    try:
        return json.loads(cfg.get("channels", "[]"))
    except Exception:
        return []

def set_channels(ch_list):
    cfg_set("channels", json.dumps(ch_list, ensure_ascii=False))

# ═══════════════════════════════════════════════════════════
#  ADMIN IDS — ENV + DB dono se milate hain
# ═══════════════════════════════════════════════════════════

def admin_ids():
    ids = set()
    # ENV se
    for x in os.getenv("ADMIN_IDS", "").split(","):
        x = x.strip()
        if x:
            try: ids.add(int(x))
            except: pass
    # DB se (bot se add kiye hue)
    cfg = cfg_get()
    for x in cfg.get("admin_ids", "").split(","):
        x = x.strip()
        if x:
            try: ids.add(int(x))
            except: pass
    return list(ids)

def add_admin(uid):
    cfg = cfg_get()
    current = cfg.get("admin_ids", "")
    existing = [x.strip() for x in current.split(",") if x.strip()]
    if str(uid) not in existing:
        existing.append(str(uid))
    cfg_set("admin_ids", ",".join(existing))

def remove_admin(uid):
    cfg = cfg_get()
    current = cfg.get("admin_ids", "")
    existing = [x.strip() for x in current.split(",") if x.strip() and x.strip() != str(uid)]
    cfg_set("admin_ids", ",".join(existing))

# ═══════════════════════════════════════════════════════════
#  KEYBOARD BUILDERS
# ═══════════════════════════════════════════════════════════

async def check_all_joined(bot, uid):
    channels = get_channels()
    not_joined = []
    for ch in channels:
        try:
            m = await bot.get_chat_member(ch["id"], uid)
            if m.status not in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
                not_joined.append(ch)
        except Exception:
            not_joined.append(ch)
    return not_joined

def kb_not_joined(channels):
    """2 Join buttons per row, phir Verify button"""
    rows = []
    pair = []
    for ch in channels:
        pair.append(InlineKeyboardButton(f"Join ↗", url=ch["link"]))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton("✅ Joined — Verify Karo", callback_data="verify_join")])
    return InlineKeyboardMarkup(rows)

def kb_after_join(channels):
    """2 channel links per row (for reference), phir Deposit Now button"""
    rows = []
    pair = []
    for ch in channels:
        pair.append(InlineKeyboardButton(f"📢 {ch.get('name', 'Channel')}", url=ch["link"]))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton("💰 Deposit Now 🎁", callback_data="deposit")])
    return InlineKeyboardMarkup(rows)

def kb_admin():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Channels Manage",   callback_data="admin_ch_list"),
         InlineKeyboardButton("➕ Channel Add",        callback_data="admin_ch_add")],
        [InlineKeyboardButton("🎙️ Voice Message",     callback_data="admin_voice_menu"),
         InlineKeyboardButton("💰 Deposit Link",      callback_data="admin_deposit_menu")],
        [InlineKeyboardButton("📝 Welcome Text",      callback_data="admin_welcome_menu"),
         InlineKeyboardButton("📝 Joined Text",       callback_data="admin_joined_text")],
        [InlineKeyboardButton("📨 Broadcast",         callback_data="admin_broadcast_menu"),
         InlineKeyboardButton("👥 Stats",             callback_data="admin_stats")],
        [InlineKeyboardButton("🚫 Block User",        callback_data="admin_block_menu"),
         InlineKeyboardButton("✅ Unblock User",      callback_data="admin_unblock_menu")],
        [InlineKeyboardButton("👑 Admin Add/Remove",  callback_data="admin_manage_admins")],
    ])

def kb_back(target="admin_panel"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=target)]])

# ═══════════════════════════════════════════════════════════
#  SEND JOINED CONTENT
# ═══════════════════════════════════════════════════════════

async def send_joined_content(bot, chat_id, user_id, cfg):
    """
    Professional 2-step flow:
      Step 1 — Voice note (with caption text, so user knows to turn sound on)
      Step 2 — Deposit message with channel links + Deposit Now button
    """
    voice_id    = cfg.get("voice_file_id", "")
    joined_text = cfg.get("joined_text", "⚠️ <b>Deposit Milega</b> — Play on Sound 🔊👆👆")
    channels    = get_channels()

    last_msg_id = None

    # ── Step 1: Voice note with caption ──────────────────
    if voice_id:
        try:
            voice_caption = "🔊 <b>Sound On Karo</b> — Important message sun lo 👆"
            await bot.send_voice(
                chat_id=chat_id,
                voice=voice_id,
                caption=voice_caption,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"Voice send failed: {e}")

    # ── Step 2: Joined text + channel links + Deposit button ──
    deposit_kb = kb_after_join(channels)
    sent = await bot.send_message(
        chat_id=chat_id,
        text=joined_text,
        reply_markup=deposit_kb,
        parse_mode=ParseMode.HTML,
    )
    last_msg_id = sent.message_id
    db_set_msg(user_id, last_msg_id)
    return sent

# ═══════════════════════════════════════════════════════════
#  /start
# ═══════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_add_user(user.id, user.username or "", user.first_name or "")

    # Purana bot message delete karo
    prev = db_get_msg(user.id)
    if prev:
        try: await context.bot.delete_message(update.effective_chat.id, prev)
        except: pass

    if db_is_blocked(user.id):
        await update.message.reply_text("🚫 Aap block hain. Admin se contact karo.")
        return

    cfg      = cfg_get()
    channels = get_channels()

    if not channels:
        sent = await update.message.reply_text("⚠️ Admin ne abhi channels set nahi kiye.")
        db_set_msg(user.id, sent.message_id)
        return

    not_joined = await check_all_joined(context.bot, user.id)

    if not_joined:
        text = cfg.get("welcome_text",
            "👋 <b>Namaste {name}!</b>\n\n🔒 Pehle saare channels join karo."
        ).format(name=user.first_name or "User")
        sent = await update.message.reply_text(
            text,
            reply_markup=kb_not_joined(not_joined),
            parse_mode=ParseMode.HTML,
        )
        db_set_msg(user.id, sent.message_id)
    else:
        await send_joined_content(
            context.bot,
            update.effective_chat.id,
            user.id,
            cfg
        )

# ═══════════════════════════════════════════════════════════
#  /admin
# ═══════════════════════════════════════════════════════════

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admin_ids(): return
    await update.message.reply_text(
        "👑 <b>Admin Panel</b>", reply_markup=kb_admin(), parse_mode=ParseMode.HTML)

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
        if db_is_blocked(user.id):
            await q.answer("🚫 Aap block hain.", show_alert=True)
            return

        not_joined = await check_all_joined(context.bot, user.id)

        if not_joined:
            # ── Abhi bhi kuch channels join nahi kiye ──
            # Show exactly which ones remain — update the message in-place
            names = "\n".join(f"• {ch.get('name', 'Channel')}" for ch in not_joined)
            await q.answer(
                f"❌ Abhi bhi {len(not_joined)} channel(s) join nahi kiye:\n{names}",
                show_alert=True
            )
            # Message update karo — sirf bache hue channels dikhao (fresh)
            cfg2 = cfg_get()
            text = cfg2.get("welcome_text",
                "👋 <b>Namaste {name}!</b>\n\n🔒 Pehle saare channels join karo."
            ).format(name=user.first_name or "User")
            try:
                await q.edit_message_text(
                    text + f"\n\n⚠️ <b>{len(not_joined)} channel(s) baaki hain — inhe join karo:</b>",
                    reply_markup=kb_not_joined(not_joined),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            return

        # ── Sab join kar liya! ──
        await q.answer("✅ Verified! Sab channels join kar liye!", show_alert=False)

        # Purana message delete karo
        try:
            await q.message.delete()
        except Exception:
            pass

        await send_joined_content(
            context.bot,
            q.message.chat_id,
            user.id,
            cfg
        )

    # ── DEPOSIT ──────────────────────────────────────────
    elif data == "deposit":
        link = cfg.get("deposit_link", "").strip()
        if not link:
            await q.answer("⚠️ Admin ne deposit link set nahi kiya.", show_alert=True)
            return
        dep_text = cfg.get("deposit_text", "💰 <b>Deposit Karo</b>\n\nNiche link pe click karo:")
        channels = get_channels()
        rows = []
        pair = []
        for ch in channels:
            pair.append(InlineKeyboardButton(f"📢 {ch.get('name','Channel')}", url=ch["link"]))
            if len(pair) == 2:
                rows.append(pair); pair = []
        if pair: rows.append(pair)
        rows.append([InlineKeyboardButton("💰 Deposit Now 🎁", url=link)])
        await q.edit_message_text(
            dep_text,
            reply_markup=InlineKeyboardMarkup(rows),
            parse_mode=ParseMode.HTML
        )

    # ══════════════════════════════════════════════════════
    #  ADMIN CALLBACKS
    # ══════════════════════════════════════════════════════
    elif data.startswith("admin_"):
        if user.id not in admin_ids():
            await q.answer("🚫 Sirf Admin ke liye!", show_alert=True)
            return

        # ── PANEL ────────────────────────────────────────
        if data == "admin_panel":
            await q.edit_message_text("👑 <b>Admin Panel</b>", reply_markup=kb_admin(), parse_mode=ParseMode.HTML)

        # ── CHANNELS LIST ────────────────────────────────
        elif data == "admin_ch_list":
            channels = get_channels()
            if not channels:
                await q.edit_message_text(
                    "📢 <b>Channels</b>\n\nKoi channel nahi hai abhi.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("➕ Add Channel", callback_data="admin_ch_add")],
                        [InlineKeyboardButton("🔙 Back", callback_data="admin_panel")],
                    ]), parse_mode=ParseMode.HTML)
                return
            text = "📢 <b>Channels List</b>\n\n"
            rows = []
            for i, ch in enumerate(channels):
                text += f"{i+1}. <b>{ch.get('name','?')}</b> — <code>{ch.get('id','?')}</code>\n"
                rows.append([InlineKeyboardButton(f"🗑️ Delete: {ch.get('name','?')}", callback_data=f"admin_ch_del_{i}")])
            rows.append([InlineKeyboardButton("➕ Add Channel", callback_data="admin_ch_add")])
            rows.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel")])
            await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode=ParseMode.HTML)

        elif data == "admin_ch_add":
            context.user_data["awaiting"] = "ch_name"
            await q.edit_message_text(
                "➕ <b>Channel Add Karo</b>\n\n<b>Step 1/3</b> — Channel ka naam bhejo:\n(e.g. <code>My Channel</code>)",
                reply_markup=kb_back("admin_ch_list"), parse_mode=ParseMode.HTML)

        elif data.startswith("admin_ch_del_"):
            idx = int(data.split("_")[-1])
            channels = get_channels()
            if 0 <= idx < len(channels):
                removed = channels.pop(idx)
                set_channels(channels)
                await q.answer(f"🗑️ '{removed.get('name','')}' delete ho gaya!", show_alert=True)
            channels = get_channels()
            if not channels:
                await q.edit_message_text("📢 Koi channel nahi.", reply_markup=kb_back("admin_panel"), parse_mode=ParseMode.HTML)
                return
            text = "📢 <b>Channels List</b>\n\n"
            rows = []
            for i, ch in enumerate(channels):
                text += f"{i+1}. <b>{ch.get('name','?')}</b> — <code>{ch.get('id','?')}</code>\n"
                rows.append([InlineKeyboardButton(f"🗑️ Delete: {ch.get('name','?')}", callback_data=f"admin_ch_del_{i}")])
            rows.append([InlineKeyboardButton("➕ Add Channel", callback_data="admin_ch_add")])
            rows.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel")])
            await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode=ParseMode.HTML)

        # ── VOICE ────────────────────────────────────────
        elif data == "admin_voice_menu":
            status = "✅ Set hai" if cfg.get("voice_file_id") else "❌ Set nahi"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎙️ Voice Upload", callback_data="admin_set_voice"),
                 InlineKeyboardButton("🗑️ Delete",       callback_data="admin_del_voice")],
                [InlineKeyboardButton("🔙 Back",          callback_data="admin_panel")],
            ])
            await q.edit_message_text(f"🎙️ <b>Voice Message</b>\n\nStatus: {status}", reply_markup=kb, parse_mode=ParseMode.HTML)

        elif data == "admin_set_voice":
            context.user_data["awaiting"] = "voice"
            await q.edit_message_text("🎙️ Voice note bhejo (voice message as audio):", reply_markup=kb_back(), parse_mode=ParseMode.HTML)

        elif data == "admin_del_voice":
            cfg_set("voice_file_id", "")
            await q.answer("🗑️ Voice delete ho gaya!", show_alert=True)
            await q.edit_message_text("👑 <b>Admin Panel</b>", reply_markup=kb_admin(), parse_mode=ParseMode.HTML)

        # ── DEPOSIT SETTINGS ─────────────────────────────
        elif data == "admin_deposit_menu":
            link = cfg.get('deposit_link', '') or 'Set nahi'
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Link Set Karo", callback_data="admin_set_deposit_link"),
                 InlineKeyboardButton("📝 Text Set Karo", callback_data="admin_set_deposit_text")],
                [InlineKeyboardButton("🔙 Back",           callback_data="admin_panel")],
            ])
            await q.edit_message_text(
                f"💰 <b>Deposit Settings</b>\n\n🔗 Link: <code>{link}</code>",
                reply_markup=kb, parse_mode=ParseMode.HTML)

        elif data == "admin_set_deposit_link":
            context.user_data["awaiting"] = "deposit_link"
            await q.edit_message_text("💰 Deposit link bhejo:", reply_markup=kb_back(), parse_mode=ParseMode.HTML)

        elif data == "admin_set_deposit_text":
            context.user_data["awaiting"] = "deposit_text"
            await q.edit_message_text("📝 Deposit page text bhejo:", reply_markup=kb_back(), parse_mode=ParseMode.HTML)

        # ── WELCOME / JOINED TEXT ────────────────────────
        elif data == "admin_welcome_menu":
            context.user_data["awaiting"] = "welcome_text"
            await q.edit_message_text(
                "📝 Welcome text bhejo.\n<code>{name}</code> = user ka naam",
                reply_markup=kb_back(), parse_mode=ParseMode.HTML)

        elif data == "admin_joined_text":
            context.user_data["awaiting"] = "joined_text"
            await q.edit_message_text(
                "📝 Join ke baad dikhne wala text bhejo:",
                reply_markup=kb_back(), parse_mode=ParseMode.HTML)

        # ── STATS ────────────────────────────────────────
        elif data == "admin_stats":
            s = db_stats()
            admins = admin_ids()
            await q.edit_message_text(
                f"📊 <b>Stats</b>\n\n"
                f"👥 Total Users: <b>{s['total']}</b>\n"
                f"🟢 Active: <b>{s['active']}</b>\n"
                f"🚫 Blocked: <b>{s['blocked']}</b>\n"
                f"📅 Aaj Joined: <b>{s['today']}</b>\n\n"
                f"👑 Admins: <b>{len(admins)}</b>",
                reply_markup=kb_back(), parse_mode=ParseMode.HTML)

        # ── BROADCAST ────────────────────────────────────
        elif data == "admin_broadcast_menu":
            context.user_data["awaiting"] = "broadcast"
            await q.edit_message_text("📨 Broadcast message type karo (HTML allowed):", reply_markup=kb_back(), parse_mode=ParseMode.HTML)

        # ── BLOCK / UNBLOCK ──────────────────────────────
        elif data == "admin_block_menu":
            context.user_data["awaiting"] = "block_user"
            await q.edit_message_text("🚫 Block karne ke liye User ID bhejo:", reply_markup=kb_back(), parse_mode=ParseMode.HTML)

        elif data == "admin_unblock_menu":
            context.user_data["awaiting"] = "unblock_user"
            await q.edit_message_text("✅ Unblock karne ke liye User ID bhejo:", reply_markup=kb_back(), parse_mode=ParseMode.HTML)

        # ── ADMIN MANAGE ─────────────────────────────────
        elif data == "admin_manage_admins":
            admins = admin_ids()
            text = "👑 <b>Admin Management</b>\n\n"
            if admins:
                text += "Current Admins:\n" + "\n".join(f"• <code>{a}</code>" for a in admins)
            else:
                text += "Koi admin nahi (sirf ENV wale hain)"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Admin Add", callback_data="admin_add_admin"),
                 InlineKeyboardButton("➖ Admin Remove", callback_data="admin_remove_admin")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin_panel")],
            ])
            await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

        elif data == "admin_add_admin":
            context.user_data["awaiting"] = "add_admin"
            await q.edit_message_text(
                "👑 Naya admin ka User ID bhejo:\n\n(User ID pata karne ke liye @userinfobot use karo)",
                reply_markup=kb_back("admin_manage_admins"), parse_mode=ParseMode.HTML)

        elif data == "admin_remove_admin":
            context.user_data["awaiting"] = "remove_admin"
            await q.edit_message_text(
                "👑 Remove karne wale admin ka User ID bhejo:",
                reply_markup=kb_back("admin_manage_admins"), parse_mode=ParseMode.HTML)

# ═══════════════════════════════════════════════════════════
#  MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════

async def msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    awaiting = context.user_data.get("awaiting", "")

    if db_is_blocked(user.id) and user.id not in admin_ids():
        await update.message.reply_text("🚫 Aap block hain.")
        return

    if user.id in admin_ids() and awaiting:
        context.user_data.pop("awaiting", None)
        msg     = update.message
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]])

        # ── VOICE ───────────────────────────────────────
        if awaiting == "voice":
            if msg.voice:
                cfg_set("voice_file_id", msg.voice.file_id)
                await msg.reply_text("✅ Voice save ho gaya!", reply_markup=back_kb)
            else:
                await msg.reply_text("❌ Voice note bhejo (audio record karke)!", reply_markup=back_kb)
            return

        # ── BROADCAST ───────────────────────────────────
        if awaiting == "broadcast":
            users  = db_all_users()
            ok = fail = 0
            sm = await msg.reply_text(f"📨 Broadcast chal raha hai... (0/{len(users)})")
            for i, uid in enumerate(users):
                try:
                    await context.bot.send_message(uid, msg.text or "", parse_mode=ParseMode.HTML)
                    ok += 1
                except:
                    fail += 1
                if (i+1) % 20 == 0:
                    try: await sm.edit_text(f"📨 Chal raha hai... ({i+1}/{len(users)})")
                    except: pass
            await sm.edit_text(
                f"📨 <b>Broadcast Done!</b>\n✅ Sent: {ok}\n❌ Failed: {fail}",
                parse_mode=ParseMode.HTML, reply_markup=back_kb)
            return

        # ── BLOCK / UNBLOCK ─────────────────────────────
        if awaiting in ("block_user", "unblock_user"):
            try:
                uid = int(msg.text.strip())
                if awaiting == "block_user":
                    db_block(uid)
                    await msg.reply_text(f"🚫 User <code>{uid}</code> block ho gaya!", parse_mode=ParseMode.HTML, reply_markup=back_kb)
                else:
                    db_unblock(uid)
                    await msg.reply_text(f"✅ User <code>{uid}</code> unblock ho gaya!", parse_mode=ParseMode.HTML, reply_markup=back_kb)
            except ValueError:
                await msg.reply_text("❌ Valid User ID dalo (sirf numbers)!", reply_markup=back_kb)
            return

        # ── ADMIN ADD/REMOVE ─────────────────────────────
        if awaiting == "add_admin":
            try:
                uid = int(msg.text.strip())
                add_admin(uid)
                await msg.reply_text(f"✅ <code>{uid}</code> admin ban gaya!", parse_mode=ParseMode.HTML, reply_markup=back_kb)
            except ValueError:
                await msg.reply_text("❌ Valid User ID dalo!", reply_markup=back_kb)
            return

        if awaiting == "remove_admin":
            try:
                uid = int(msg.text.strip())
                remove_admin(uid)
                await msg.reply_text(f"✅ <code>{uid}</code> admin se remove ho gaya!", parse_mode=ParseMode.HTML, reply_markup=back_kb)
            except ValueError:
                await msg.reply_text("❌ Valid User ID dalo!", reply_markup=back_kb)
            return

        # ── CHANNEL ADD: 3-step ──────────────────────────
        if awaiting == "ch_name":
            context.user_data["new_ch_name"] = msg.text.strip()
            context.user_data["awaiting"]    = "ch_id"
            await msg.reply_text(
                "➕ <b>Step 2/3</b> — Channel ka <b>ID</b> bhejo\n"
                "(e.g. <code>-1001234567890</code>)\n\n"
                "💡 ID kaise pata kare: Channel ka koi message @userinfobot ko forward karo",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]]))
            return

        if awaiting == "ch_id":
            context.user_data["new_ch_id"] = msg.text.strip()
            context.user_data["awaiting"]  = "ch_link"
            await msg.reply_text(
                "➕ <b>Step 3/3</b> — Channel ka <b>Link</b> bhejo\n"
                "(e.g. <code>https://t.me/yourchannel</code>)",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]]))
            return

        if awaiting == "ch_link":
            ch_name = context.user_data.pop("new_ch_name", "Channel")
            ch_id   = context.user_data.pop("new_ch_id",   "")
            ch_link = msg.text.strip()
            channels = get_channels()
            channels.append({"name": ch_name, "id": ch_id, "link": ch_link})
            set_channels(channels)
            await msg.reply_text(
                f"✅ <b>Channel add ho gaya!</b>\n\n"
                f"📢 Naam: <b>{ch_name}</b>\n"
                f"🆔 ID: <code>{ch_id}</code>\n"
                f"🔗 Link: {ch_link}\n\n"
                f"Total channels: <b>{len(channels)}</b>",
                parse_mode=ParseMode.HTML, reply_markup=back_kb)
            return

        # ── TEXT CONFIG KEYS ────────────────────────────
        key_map = {
            "deposit_link": "deposit_link",
            "deposit_text": "deposit_text",
            "welcome_text": "welcome_text",
            "joined_text":  "joined_text",
        }
        if awaiting in key_map:
            cfg_set(key_map[awaiting], msg.text.strip())
            await msg.reply_text(
                f"✅ <b>{awaiting.replace('_',' ').title()}</b> update ho gaya!",
                parse_mode=ParseMode.HTML, reply_markup=back_kb)

# ═══════════════════════════════════════════════════════════
#  MAIN — Python 3.14 compatible
# ═══════════════════════════════════════════════════════════

async def run_bot():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN set nahi hai!")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CallbackQueryHandler(cb_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, msg_handler))

    logger.info("✅ Bot chal raha hai...")

    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

def main():
    init_db()
    start_keep_alive(int(os.getenv("PORT", 10000)))
    asyncio.run(run_bot())

if __name__ == "__main__":
    main()
