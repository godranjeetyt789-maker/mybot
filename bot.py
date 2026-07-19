"""
╔══════════════════════════════════════════════════════════════════════╗
║     ULTRA PREMIUM FORCE-JOIN BOT  —  VERSION 3.0 COMPLETE          ║
║     Set 1 → Force Join  |  Set 2 → After Join (Deposit)            ║
║     ✅ Full Named Buttons | Custom Alert | Premium Flow | Advanced  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os, asyncio, sqlite3, threading, logging, json
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

# ═══════════════════════════════════════════════════════════════════
#  KEEP-ALIVE SERVER
# ═══════════════════════════════════════════════════════════════════

class _Ping(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *a): pass

def start_keep_alive(port=10000):
    threading.Thread(
        target=HTTPServer(("0.0.0.0", port), _Ping).serve_forever,
        daemon=True
    ).start()
    logger.info(f"Keep-alive server: port {port}")

# ═══════════════════════════════════════════════════════════════════
#  DATABASE SETUP
# ═══════════════════════════════════════════════════════════════════

def _conn(): return sqlite3.connect(DB_PATH)

def init_db():
    with _conn() as c:
        # Users table
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id      INTEGER PRIMARY KEY,
            username     TEXT    DEFAULT '',
            first_name   TEXT    DEFAULT '',
            joined_date  TEXT    DEFAULT '',
            is_blocked   INTEGER DEFAULT 0,
            last_bot_msg INTEGER DEFAULT 0,
            join_count   INTEGER DEFAULT 0
        )""")
        # Config table
        c.execute("""CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        )""")
        defaults = {
            # ── User facing texts ──
            "welcome_text": (
                "🔐 <b>Hey {name}! Welcome to Free Recharge Bot</b> 💸\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🎁 <b>Tumhara ₹500 Reward Ready Hai!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "⚡ <b>Reward Unlock Karne Ke Liye:</b>\n"
                "  ✅ Niche diye <b>saare channels</b> join karo\n"
                "  🔓 Phir <b>Verify &amp; Claim</b> button dabao\n\n"
                "👇 <b>Abhi join karo:</b>"
            ),
            "joined_text": (
                "🔊 <b>Sound On Karo — Important Message Sun Lo!</b> 👆\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ <b>Deposit Milega — Play on Sound</b> 🎙️👆\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "👇 <b>Deposit karne ke liye click karo:</b>"
            ),
            "deposit_text": (
                "🎁 <b>Deposit Karo — Reward Unlock Karo!</b>\n\n"
                "💸 Pehli deposit pe <b>BONUS</b> milega!\n\n"
                "👇 Niche button pe click karo:"
            ),
            # ── Alert messages (popup) ──
            "alert_not_joined": "❌ Pehle saare channels join karo! Phir Verify karo.",
            "alert_blocked":    "🚫 Aap block hain. Admin se contact karo.",
            # ── Links ──
            "deposit_link":  "",
            "voice_file_id": "",
            # ── Channel sets ──
            "channels":       "[]",
            "channels_after": "[]",
            # ── Admin IDs ──
            "admin_ids": "",
            # ── Button labels ──
            "btn_verify_label":  "✅ Verify & Claim Reward 🎁",
            "btn_deposit_label": "🚀 Deposit Karo & Reward Pao 💰",
            # ── Join button style: "naam_only" / "naam_arrow" / "join_naam" / "custom" ──
            "join_btn_style":  "naam_only",
            "join_btn_prefix": "👉",
            # ── Buttons per row: "1" or "2" ──
            "btns_per_row": "2",
        }
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO config (key,value) VALUES (?,?)", (k, v))
        c.commit()

# ── User helpers ──────────────────────────────────────────────────
def db_add_user(uid, uname, fname):
    with _conn() as c:
        c.execute("""
            INSERT INTO users (user_id,username,first_name,joined_date,join_count)
            VALUES (?,?,?,?,1)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                join_count=join_count+1
        """, (uid, uname, fname, str(date.today())))
        c.commit()

def db_all_users():
    with _conn() as c:
        return [r[0] for r in c.execute(
            "SELECT user_id FROM users WHERE is_blocked=0").fetchall()]

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
        today   = c.execute("SELECT COUNT(*) FROM users WHERE joined_date=?",
                            (str(date.today()),)).fetchone()[0]
    return {"total": total, "active": active, "blocked": blocked, "today": today}

def db_search_user(uid):
    with _conn() as c:
        r = c.execute(
            "SELECT user_id,username,first_name,joined_date,is_blocked,join_count FROM users WHERE user_id=?",
            (uid,)).fetchone()
    return r

# ═══════════════════════════════════════════════════════════════════
#  CONFIG HELPERS
# ═══════════════════════════════════════════════════════════════════

def cfg_get():
    with _conn() as c:
        return dict(c.execute("SELECT key,value FROM config").fetchall())

def cfg_set(key, value):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO config (key,value) VALUES (?,?)", (key, value))
        c.commit()

def get_channels(key="channels"):
    try:
        return json.loads(cfg_get().get(key, "[]"))
    except Exception:
        return []

def set_channels(ch_list, key="channels"):
    cfg_set(key, json.dumps(ch_list, ensure_ascii=False))

def admin_ids():
    ids = set()
    for src in [os.getenv("ADMIN_IDS", ""), cfg_get().get("admin_ids", "")]:
        for x in src.split(","):
            x = x.strip()
            if x:
                try: ids.add(int(x))
                except: pass
    return list(ids)

def add_admin(uid):
    cfg = cfg_get()
    existing = [x.strip() for x in cfg.get("admin_ids", "").split(",") if x.strip()]
    if str(uid) not in existing:
        existing.append(str(uid))
    cfg_set("admin_ids", ",".join(existing))

def remove_admin(uid):
    cfg = cfg_get()
    existing = [x.strip() for x in cfg.get("admin_ids", "").split(",")
                if x.strip() and x.strip() != str(uid)]
    cfg_set("admin_ids", ",".join(existing))

# ═══════════════════════════════════════════════════════════════════
#  FORCE-JOIN CHECK
# ═══════════════════════════════════════════════════════════════════

async def check_not_joined(bot, uid):
    not_joined = []
    for ch in get_channels("channels"):
        try:
            m = await bot.get_chat_member(ch["id"], uid)
            if m.status not in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER):
                not_joined.append(ch)
        except Exception:
            not_joined.append(ch)
    return not_joined

# ═══════════════════════════════════════════════════════════════════
#  KEYBOARD BUILDERS
# ═══════════════════════════════════════════════════════════════════

def _join_btn_label(ch, cfg):
    """
    Channel join button ka label:
    - naam_only  → sirf channel naam (admin ka diya hua)
    - naam_arrow → Channel Naam ↗
    - join_naam  → Join Channel Naam
    - custom     → [prefix] Channel Naam
    """
    style  = cfg.get("join_btn_style", "naam_only")
    prefix = cfg.get("join_btn_prefix", "👉").strip()
    name   = ch.get("name", "Channel").strip()

    if style == "naam_arrow":
        return f"{name} ↗"
    elif style == "join_naam":
        return f"Join {name}"
    elif style == "custom" and prefix:
        return f"{prefix} {name}"
    else:
        return name  # naam_only — sirf naam, koi extra nahi

def _build_channel_buttons(channels, cfg):
    """Channels ki rows banata hai — 1 ya 2 per row as per config."""
    per_row = int(cfg.get("btns_per_row", "2"))
    rows, pair = [], []
    for ch in channels:
        label = _join_btn_label(ch, cfg)
        pair.append(InlineKeyboardButton(label, url=ch.get("link", "https://t.me/")))
        if len(pair) == per_row:
            rows.append(pair); pair = []
    if pair:
        rows.append(pair)
    return rows

def kb_force_join(not_joined, cfg):
    rows = _build_channel_buttons(not_joined, cfg)
    verify_label = cfg.get("btn_verify_label", "✅ Verify & Claim Reward 🎁")
    rows.append([InlineKeyboardButton(verify_label, callback_data="verify_join")])
    return InlineKeyboardMarkup(rows)

def kb_after_join(deposit_link, cfg):
    after_chs = get_channels("channels_after")
    rows = _build_channel_buttons(after_chs, cfg)
    deposit_label = cfg.get("btn_deposit_label", "🚀 Deposit Karo & Reward Pao 💰")
    rows.append([InlineKeyboardButton(
        deposit_label,
        url=deposit_link if deposit_link else "https://t.me/"
    )])
    return InlineKeyboardMarkup(rows)

def kb_admin():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Set-1 Ch (Force Join)", callback_data="admin_ch1_list"),
         InlineKeyboardButton("➕ Add Set-1",              callback_data="admin_ch1_add")],
        [InlineKeyboardButton("📣 Set-2 Ch (Deposit)",    callback_data="admin_ch2_list"),
         InlineKeyboardButton("➕ Add Set-2",              callback_data="admin_ch2_add")],
        [InlineKeyboardButton("🎙️ Voice Message",          callback_data="admin_voice_menu"),
         InlineKeyboardButton("💰 Deposit Link",           callback_data="admin_deposit_menu")],
        [InlineKeyboardButton("📝 Welcome Text",           callback_data="admin_welcome_menu"),
         InlineKeyboardButton("📝 Joined Text",            callback_data="admin_joined_text")],
        [InlineKeyboardButton("🔘 Button Labels",          callback_data="admin_btn_labels"),
         InlineKeyboardButton("✏️ Join Btn Style",         callback_data="admin_join_style")],
        [InlineKeyboardButton("💬 Alert Messages",         callback_data="admin_alerts"),
         InlineKeyboardButton("🔢 Buttons Per Row",        callback_data="admin_btn_row")],
        [InlineKeyboardButton("📨 Broadcast",              callback_data="admin_broadcast_menu"),
         InlineKeyboardButton("📊 Stats",                  callback_data="admin_stats")],
        [InlineKeyboardButton("🚫 Block User",             callback_data="admin_block_menu"),
         InlineKeyboardButton("✅ Unblock User",           callback_data="admin_unblock_menu")],
        [InlineKeyboardButton("🔍 User Search",            callback_data="admin_search_user"),
         InlineKeyboardButton("👑 Admin Manage",           callback_data="admin_manage_admins")],
    ])

def kb_back(target="admin_panel"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=target)]])

# ═══════════════════════════════════════════════════════════════════
#  CHANNEL LIST (Admin display)
# ═══════════════════════════════════════════════════════════════════

async def show_ch_list(q, set_key, set_label, add_cb, del_prefix, back_cb="admin_panel"):
    channels = get_channels(set_key)
    if not channels:
        await q.edit_message_text(
            f"📢 <b>{set_label}</b>\n\nKoi channel nahi hai abhi.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Add Channel", callback_data=add_cb)],
                [InlineKeyboardButton("🔙 Back", callback_data=back_cb)],
            ]), parse_mode=ParseMode.HTML)
        return
    text = f"📢 <b>{set_label}</b>\n\n"
    rows = []
    for i, ch in enumerate(channels):
        text += f"{i+1}. <b>{ch.get('name','?')}</b> | <code>{ch.get('id','?')}</code>\n"
        rows.append([InlineKeyboardButton(
            f"🗑️ {ch.get('name','?')}", callback_data=f"{del_prefix}{i}")])
    rows.append([InlineKeyboardButton("➕ Add Channel", callback_data=add_cb)])
    rows.append([InlineKeyboardButton("🔙 Back", callback_data=back_cb)])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows),
                              parse_mode=ParseMode.HTML)

# ═══════════════════════════════════════════════════════════════════
#  PREMIUM UNLOCK FLOW
# ═══════════════════════════════════════════════════════════════════

async def send_joined_content(bot, chat_id, user_id, cfg):
    voice_id     = cfg.get("voice_file_id", "")
    joined_text  = cfg.get("joined_text", "✅ <b>Sab Channels Join Ho Gaye!</b>")
    deposit_link = cfg.get("deposit_link", "").strip()

    # Step 1: Unlock animation
    anim = await bot.send_message(
        chat_id=chat_id,
        text="🔓 <b>Reward Unlock Ho Raha Hai...</b>\n\n⏳ Please wait...",
        parse_mode=ParseMode.HTML,
    )
    await asyncio.sleep(1.2)
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=anim.message_id,
            text=(
                "🎉 <b>Congratulations! Reward Unlock Ho Gaya!</b>\n\n"
                "✅ Saare channels join kar liye!\n"
                "🔊 <b>Ab sound on karo aur niche dekho</b> 👇"
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass
    await asyncio.sleep(0.8)

    # Step 2: Voice note
    if voice_id:
        try:
            await bot.send_voice(
                chat_id=chat_id,
                voice=voice_id,
                caption="🔊 <b>Sound On Karo</b> — Yeh message zaroor suno! 🎙️👆",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"Voice send failed: {e}")

    # Step 3: Main content + deposit
    sent = await bot.send_message(
        chat_id=chat_id,
        text=joined_text,
        reply_markup=kb_after_join(deposit_link, cfg),
        parse_mode=ParseMode.HTML,
    )
    db_set_msg(user_id, sent.message_id)

# ═══════════════════════════════════════════════════════════════════
#  /start COMMAND
# ═══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_add_user(user.id, user.username or "", user.first_name or "")

    prev = db_get_msg(user.id)
    if prev:
        try: await context.bot.delete_message(update.effective_chat.id, prev)
        except: pass

    if db_is_blocked(user.id):
        await update.message.reply_text("🚫 Aap block hain. Admin se contact karo.")
        return

    cfg      = cfg_get()
    ch1_list = get_channels("channels")

    if not ch1_list:
        sent = await update.message.reply_text(
            "⚠️ <b>Bot Setup Pending</b>\n\nAdmin ne abhi channels set nahi kiye.",
            parse_mode=ParseMode.HTML)
        db_set_msg(user.id, sent.message_id)
        return

    not_joined = await check_not_joined(context.bot, user.id)

    if not_joined:
        text = cfg.get("welcome_text", "🔐 <b>Hey {name}!</b> Channels join karo.").format(
            name=user.first_name or "User")
        sent = await update.message.reply_text(
            text,
            reply_markup=kb_force_join(not_joined, cfg),
            parse_mode=ParseMode.HTML,
        )
        db_set_msg(user.id, sent.message_id)
    else:
        await send_joined_content(context.bot, update.effective_chat.id, user.id, cfg)

# ═══════════════════════════════════════════════════════════════════
#  /admin COMMAND
# ═══════════════════════════════════════════════════════════════════

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admin_ids(): return
    s   = db_stats()
    ch1 = get_channels("channels")
    ch2 = get_channels("channels_after")
    cfg = cfg_get()
    voice = "✅" if cfg.get("voice_file_id") else "❌"
    dlink = "✅" if cfg.get("deposit_link")  else "❌"
    await update.message.reply_text(
        f"👑 <b>Admin Panel — Free Recharge Bot</b>\n\n"
        f"👥 Total Users : <b>{s['total']}</b>  |  🟢 Active: <b>{s['active']}</b>\n"
        f"📅 Aaj Joined  : <b>{s['today']}</b>  |  🚫 Blocked: <b>{s['blocked']}</b>\n\n"
        f"📢 Set-1 Ch : <b>{len(ch1)}</b>  |  📣 Set-2 Ch: <b>{len(ch2)}</b>\n"
        f"🎙️ Voice: {voice}  |  💰 Deposit Link: {dlink}",
        reply_markup=kb_admin(), parse_mode=ParseMode.HTML)

# ═══════════════════════════════════════════════════════════════════
#  CALLBACK HANDLER
# ═══════════════════════════════════════════════════════════════════

async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    user = q.from_user
    data = q.data
    cfg  = cfg_get()
    await q.answer()

    if data == "noop":
        return

    # ════════════════════════════════════════════════
    #  VERIFY JOIN (User side)
    # ════════════════════════════════════════════════
    if data == "verify_join":
        if db_is_blocked(user.id):
            alert_msg = cfg.get("alert_blocked", "🚫 Aap block hain.")
            await q.answer(alert_msg, show_alert=True)
            return

        not_joined = await check_not_joined(context.bot, user.id)

        if not_joined:
            alert_msg = cfg.get("alert_not_joined",
                "❌ Pehle saare channels join karo! Phir Verify karo.")
            await q.answer(alert_msg, show_alert=True)

            # Refresh karke sirf baaki wale channels dikhao
            try: await q.message.delete()
            except: pass
            cfg2      = cfg_get()
            base_text = cfg2.get("welcome_text",
                "🔐 <b>Hey {name}!</b>\n\nChannels join karo."
            ).format(name=user.first_name or "User")
            count = len(not_joined)
            sent = await context.bot.send_message(
                chat_id=q.message.chat_id,
                text=(
                    base_text
                    + f"\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    + f"⚠️ <b>Abhi bhi {count} channel join karna baaki hai!</b>\n"
                    + "👇 <b>Inhe join karo phir verify karo:</b>"
                ),
                reply_markup=kb_force_join(not_joined, cfg2),
                parse_mode=ParseMode.HTML,
            )
            db_set_msg(user.id, sent.message_id)
            return

        try: await q.message.delete()
        except: pass
        await send_joined_content(context.bot, q.message.chat_id, user.id, cfg)
        return

    # ════════════════════════════════════════════════
    #  ADMIN SECTION
    # ════════════════════════════════════════════════
    if not data.startswith("admin_"):
        return

    if user.id not in admin_ids():
        await q.answer("🚫 Sirf Admin ke liye!", show_alert=True)
        return

    # ── PANEL ─────────────────────────────────────────
    if data == "admin_panel":
        s   = db_stats()
        ch1 = get_channels("channels")
        ch2 = get_channels("channels_after")
        await q.edit_message_text(
            f"👑 <b>Admin Panel</b>\n\n"
            f"👥 Total: <b>{s['total']}</b>  |  🟢 Active: <b>{s['active']}</b>\n"
            f"📅 Aaj: <b>{s['today']}</b>  |  🚫 Blocked: <b>{s['blocked']}</b>\n"
            f"📢 Set-1: <b>{len(ch1)}</b>  |  📣 Set-2: <b>{len(ch2)}</b>",
            reply_markup=kb_admin(), parse_mode=ParseMode.HTML)

    # ── SET-1 CHANNELS ─────────────────────────────────
    elif data == "admin_ch1_list":
        await show_ch_list(q, "channels", "Set-1 Channels (Force Join)",
                           "admin_ch1_add", "admin_ch1_del_")

    elif data == "admin_ch1_add":
        context.user_data["awaiting"]   = "ch_name"
        context.user_data["ch_set_key"] = "channels"
        await q.edit_message_text(
            "➕ <b>Set-1 Channel Add</b>\n\n"
            "<b>Step 1/3</b> — Channel ka <b>naam</b> type karo:\n"
            "⚠️ Yahi naam button pe dikhega!\n"
            "(e.g. <code>Earn With Komal</code>)",
            reply_markup=kb_back("admin_ch1_list"), parse_mode=ParseMode.HTML)

    elif data.startswith("admin_ch1_del_"):
        idx = int(data.replace("admin_ch1_del_", ""))
        chs = get_channels("channels")
        if 0 <= idx < len(chs):
            removed = chs.pop(idx)
            set_channels(chs, "channels")
            await q.answer(f"🗑️ '{removed.get('name','')}' delete!", show_alert=True)
        await show_ch_list(q, "channels", "Set-1 Channels (Force Join)",
                           "admin_ch1_add", "admin_ch1_del_")

    # ── SET-2 CHANNELS ─────────────────────────────────
    elif data == "admin_ch2_list":
        await show_ch_list(q, "channels_after", "Set-2 Channels (Deposit Screen)",
                           "admin_ch2_add", "admin_ch2_del_")

    elif data == "admin_ch2_add":
        context.user_data["awaiting"]   = "ch_name"
        context.user_data["ch_set_key"] = "channels_after"
        await q.edit_message_text(
            "➕ <b>Set-2 Channel Add</b>\n\n"
            "<b>Step 1/3</b> — Channel ka <b>naam</b> type karo:\n"
            "⚠️ Yahi naam button pe dikhega!\n"
            "(e.g. <code>Deposit Channel</code>)",
            reply_markup=kb_back("admin_ch2_list"), parse_mode=ParseMode.HTML)

    elif data.startswith("admin_ch2_del_"):
        idx = int(data.replace("admin_ch2_del_", ""))
        chs = get_channels("channels_after")
        if 0 <= idx < len(chs):
            removed = chs.pop(idx)
            set_channels(chs, "channels_after")
            await q.answer(f"🗑️ '{removed.get('name','')}' delete!", show_alert=True)
        await show_ch_list(q, "channels_after", "Set-2 Channels (Deposit Screen)",
                           "admin_ch2_add", "admin_ch2_del_")

    # ── VOICE ──────────────────────────────────────────
    elif data == "admin_voice_menu":
        status = "✅ Set hai" if cfg.get("voice_file_id") else "❌ Set nahi"
        await q.edit_message_text(
            f"🎙️ <b>Voice Message</b>\n\nStatus: {status}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎙️ Upload Voice", callback_data="admin_set_voice"),
                 InlineKeyboardButton("🗑️ Delete",       callback_data="admin_del_voice")],
                [InlineKeyboardButton("🔙 Back",          callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data == "admin_set_voice":
        context.user_data["awaiting"] = "voice"
        await q.edit_message_text(
            "🎙️ Voice note bhejo (record karke):",
            reply_markup=kb_back(), parse_mode=ParseMode.HTML)

    elif data == "admin_del_voice":
        cfg_set("voice_file_id", "")
        await q.answer("🗑️ Voice delete!", show_alert=True)
        await q.edit_message_text(
            "👑 <b>Admin Panel</b>", reply_markup=kb_admin(), parse_mode=ParseMode.HTML)

    # ── DEPOSIT ────────────────────────────────────────
    elif data == "admin_deposit_menu":
        link = cfg.get("deposit_link", "") or "Set nahi"
        await q.edit_message_text(
            f"💰 <b>Deposit Settings</b>\n\n🔗 Link: <code>{link}</code>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Link Set Karo", callback_data="admin_set_deposit_link"),
                 InlineKeyboardButton("📝 Text Set Karo", callback_data="admin_set_deposit_text")],
                [InlineKeyboardButton("🔙 Back",          callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data == "admin_set_deposit_link":
        context.user_data["awaiting"] = "deposit_link"
        await q.edit_message_text(
            "💰 Deposit link bhejo:", reply_markup=kb_back(), parse_mode=ParseMode.HTML)

    elif data == "admin_set_deposit_text":
        context.user_data["awaiting"] = "deposit_text"
        await q.edit_message_text(
            "📝 Deposit screen text bhejo:", reply_markup=kb_back(), parse_mode=ParseMode.HTML)

    # ── WELCOME / JOINED TEXT ──────────────────────────
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

    # ── BUTTON LABELS ──────────────────────────────────
    elif data == "admin_btn_labels":
        v = cfg.get("btn_verify_label", "✅ Verify & Claim Reward 🎁")
        d = cfg.get("btn_deposit_label", "🚀 Deposit Karo & Reward Pao 💰")
        await q.edit_message_text(
            f"🔘 <b>Button Labels</b>\n\n"
            f"✅ Verify Button:\n<code>{v}</code>\n\n"
            f"💰 Deposit Button:\n<code>{d}</code>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ Verify Btn",  callback_data="admin_set_verify_label"),
                 InlineKeyboardButton("✏️ Deposit Btn", callback_data="admin_set_deposit_label")],
                [InlineKeyboardButton("🔙 Back",         callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data == "admin_set_verify_label":
        context.user_data["awaiting"] = "btn_verify_label"
        await q.edit_message_text(
            "✏️ Verify button ka naya text bhejo:\n(e.g. <code>✅ Claim Karo</code>)",
            reply_markup=kb_back("admin_btn_labels"), parse_mode=ParseMode.HTML)

    elif data == "admin_set_deposit_label":
        context.user_data["awaiting"] = "btn_deposit_label"
        await q.edit_message_text(
            "✏️ Deposit button ka naya text bhejo:\n(e.g. <code>💸 Abhi Deposit Karo</code>)",
            reply_markup=kb_back("admin_btn_labels"), parse_mode=ParseMode.HTML)

    # ── JOIN BUTTON STYLE ──────────────────────────────
    elif data == "admin_join_style":
        style  = cfg.get("join_btn_style", "naam_only")
        prefix = cfg.get("join_btn_prefix", "👉")
        await q.edit_message_text(
            f"✏️ <b>Join Button Style</b>\n\n"
            f"Current: <b>{style}</b>  |  Prefix: <code>{prefix}</code>\n\n"
            f"<b>naam_only</b>  → <code>Earn With Komal</code>\n"
            f"<b>naam_arrow</b> → <code>Earn With Komal ↗</code>\n"
            f"<b>join_naam</b>  → <code>Join Earn With Komal</code>\n"
            f"<b>custom</b>     → <code>👉 Earn With Komal</code>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Naam Only",  callback_data="admin_jstyle_naam_only"),
                 InlineKeyboardButton("Naam ↗",     callback_data="admin_jstyle_naam_arrow")],
                [InlineKeyboardButton("Join Naam",  callback_data="admin_jstyle_join_naam"),
                 InlineKeyboardButton("Custom Prefix", callback_data="admin_jstyle_custom")],
                [InlineKeyboardButton("🔙 Back",    callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data in ("admin_jstyle_naam_only", "admin_jstyle_naam_arrow", "admin_jstyle_join_naam"):
        style_map = {
            "admin_jstyle_naam_only":  "naam_only",
            "admin_jstyle_naam_arrow": "naam_arrow",
            "admin_jstyle_join_naam":  "join_naam",
        }
        cfg_set("join_btn_style", style_map[data])
        await q.answer(f"✅ Style set: {style_map[data]}", show_alert=True)
        await q.edit_message_text("👑 <b>Admin Panel</b>",
                                   reply_markup=kb_admin(), parse_mode=ParseMode.HTML)

    elif data == "admin_jstyle_custom":
        context.user_data["awaiting"] = "join_btn_prefix"
        await q.edit_message_text(
            "✏️ Custom prefix bhejo jo button ke aage lage:\n"
            "(e.g. <code>👉</code> ya <code>📢</code> ya <code>Join</code>)",
            reply_markup=kb_back("admin_join_style"), parse_mode=ParseMode.HTML)

    # ── ALERT MESSAGES ─────────────────────────────────
    elif data == "admin_alerts":
        nj = cfg.get("alert_not_joined", "")
        bl = cfg.get("alert_blocked", "")
        await q.edit_message_text(
            f"💬 <b>Alert Messages (Popup)</b>\n\n"
            f"❌ Not Joined Alert:\n<code>{nj}</code>\n\n"
            f"🚫 Blocked Alert:\n<code>{bl}</code>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ Not Joined Alert", callback_data="admin_set_alert_nj"),
                 InlineKeyboardButton("✏️ Blocked Alert",    callback_data="admin_set_alert_bl")],
                [InlineKeyboardButton("🔙 Back",              callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data == "admin_set_alert_nj":
        context.user_data["awaiting"] = "alert_not_joined"
        await q.edit_message_text(
            "💬 'Channel join nahi kiya' wala alert text bhejo:\n"
            "(e.g. <code>❌ Pehle join karo!</code>)",
            reply_markup=kb_back("admin_alerts"), parse_mode=ParseMode.HTML)

    elif data == "admin_set_alert_bl":
        context.user_data["awaiting"] = "alert_blocked"
        await q.edit_message_text(
            "💬 'Block' wala alert text bhejo:\n"
            "(e.g. <code>🚫 Aap block hain!</code>)",
            reply_markup=kb_back("admin_alerts"), parse_mode=ParseMode.HTML)

    # ── BUTTONS PER ROW ────────────────────────────────
    elif data == "admin_btn_row":
        cur = cfg.get("btns_per_row", "2")
        await q.edit_message_text(
            f"🔢 <b>Buttons Per Row</b>\n\nCurrent: <b>{cur} per row</b>\n\n"
            f"Join channel buttons ek row mein kitne chahiye?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("1️⃣ Ek (Full Width)", callback_data="admin_bpr_1"),
                 InlineKeyboardButton("2️⃣ Do (Default)",    callback_data="admin_bpr_2")],
                [InlineKeyboardButton("🔙 Back",             callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data == "admin_bpr_1":
        cfg_set("btns_per_row", "1")
        await q.answer("✅ Ek button per row!", show_alert=True)
        await q.edit_message_text("👑 <b>Admin Panel</b>",
                                   reply_markup=kb_admin(), parse_mode=ParseMode.HTML)

    elif data == "admin_bpr_2":
        cfg_set("btns_per_row", "2")
        await q.answer("✅ Do button per row!", show_alert=True)
        await q.edit_message_text("👑 <b>Admin Panel</b>",
                                   reply_markup=kb_admin(), parse_mode=ParseMode.HTML)

    # ── STATS ──────────────────────────────────────────
    elif data == "admin_stats":
        s      = db_stats()
        admins = admin_ids()
        ch1    = get_channels("channels")
        ch2    = get_channels("channels_after")
        voice  = "✅ Set" if cfg.get("voice_file_id") else "❌ Nahi"
        dlink  = "✅ Set" if cfg.get("deposit_link")  else "❌ Nahi"
        style  = cfg.get("join_btn_style", "naam_only")
        bpr    = cfg.get("btns_per_row", "2")
        await q.edit_message_text(
            f"📊 <b>Bot Complete Stats</b>\n\n"
            f"👥 Total Users  : <b>{s['total']}</b>\n"
            f"🟢 Active       : <b>{s['active']}</b>\n"
            f"🚫 Blocked      : <b>{s['blocked']}</b>\n"
            f"📅 Aaj Joined   : <b>{s['today']}</b>\n\n"
            f"📢 Set-1 Ch     : <b>{len(ch1)}</b>\n"
            f"📣 Set-2 Ch     : <b>{len(ch2)}</b>\n"
            f"🎙️ Voice        : {voice}\n"
            f"💰 Deposit Link  : {dlink}\n"
            f"🔘 Btn Style    : <b>{style}</b>\n"
            f"🔢 Btns/Row     : <b>{bpr}</b>\n"
            f"👑 Admins       : <b>{len(admins)}</b>",
            reply_markup=kb_back(), parse_mode=ParseMode.HTML)

    # ── BROADCAST ──────────────────────────────────────
    elif data == "admin_broadcast_menu":
        await q.edit_message_text(
            "📨 <b>Broadcast</b>\n\nKaunsa type?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Text",  callback_data="admin_bcast_text"),
                 InlineKeyboardButton("🖼️ Photo", callback_data="admin_bcast_photo")],
                [InlineKeyboardButton("🎥 Video", callback_data="admin_bcast_video"),
                 InlineKeyboardButton("🔙 Back",  callback_data="admin_panel")],
            ]), parse_mode=ParseMode.HTML)

    elif data in ("admin_bcast_text", "admin_bcast_photo", "admin_bcast_video"):
        btype = data.replace("admin_bcast_", "")
        context.user_data["awaiting"]       = "broadcast"
        context.user_data["broadcast_type"] = btype
        hint = {
            "text":  "📝 Text bhejo (HTML allowed):",
            "photo": "🖼️ Photo bhejo (caption optional):",
            "video": "🎥 Video bhejo (caption optional):",
        }
        await q.edit_message_text(hint.get(btype, "Message bhejo:"),
                                   reply_markup=kb_back("admin_broadcast_menu"),
                                   parse_mode=ParseMode.HTML)

    # ── BLOCK / UNBLOCK ────────────────────────────────
    elif data == "admin_block_menu":
        context.user_data["awaiting"] = "block_user"
        await q.edit_message_text("🚫 Block karne ke liye User ID bhejo:",
                                   reply_markup=kb_back(), parse_mode=ParseMode.HTML)

    elif data == "admin_unblock_menu":
        context.user_data["awaiting"] = "unblock_user"
        await q.edit_message_text("✅ Unblock karne ke liye User ID bhejo:",
                                   reply_markup=kb_back(), parse_mode=ParseMode.HTML)

    # ── USER SEARCH ────────────────────────────────────
    elif data == "admin_search_user":
        context.user_data["awaiting"] = "search_user"
        await q.edit_message_text("🔍 User ID bhejo jise search karna hai:",
                                   reply_markup=kb_back(), parse_mode=ParseMode.HTML)

    # ── ADMIN MANAGE ───────────────────────────────────
    elif data == "admin_manage_admins":
        admins = admin_ids()
        text   = "👑 <b>Admin Management</b>\n\n"
        text  += ("Admins:\n" + "\n".join(f"• <code>{a}</code>" for a in admins)
                  if admins else "Koi admin nahi (ENV se chal raha)")
        await q.edit_message_text(text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Add Admin",    callback_data="admin_add_admin"),
                 InlineKeyboardButton("➖ Remove Admin", callback_data="admin_remove_admin")],
                [InlineKeyboardButton("🔙 Back",         callback_data="admin_panel")],
            ]))

    elif data == "admin_add_admin":
        context.user_data["awaiting"] = "add_admin"
        await q.edit_message_text(
            "👑 Naya admin ka User ID bhejo:\n(@userinfobot se pata karo)",
            reply_markup=kb_back("admin_manage_admins"), parse_mode=ParseMode.HTML)

    elif data == "admin_remove_admin":
        context.user_data["awaiting"] = "remove_admin"
        await q.edit_message_text("👑 Remove karne wale admin ka ID bhejo:",
                                   reply_markup=kb_back("admin_manage_admins"),
                                   parse_mode=ParseMode.HTML)

# ═══════════════════════════════════════════════════════════════════
#  MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════════

async def msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    awaiting = context.user_data.get("awaiting", "")

    if db_is_blocked(user.id) and user.id not in admin_ids():
        await update.message.reply_text("🚫 Aap block hain.")
        return

    if user.id not in admin_ids() or not awaiting:
        return

    context.user_data.pop("awaiting", None)
    msg     = update.message
    back_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")]])

    # ── VOICE ────────────────────────────────────────
    if awaiting == "voice":
        if msg.voice:
            cfg_set("voice_file_id", msg.voice.file_id)
            await msg.reply_text("✅ Voice save ho gaya!", reply_markup=back_kb)
        else:
            await msg.reply_text("❌ Voice note bhejo (record karke)!", reply_markup=back_kb)
        return

    # ── BROADCAST ────────────────────────────────────
    if awaiting == "broadcast":
        users  = db_all_users()
        btype  = context.user_data.pop("broadcast_type", "text")
        ok = fail = 0
        sm = await msg.reply_text(f"📨 Broadcast chal raha hai... (0/{len(users)})")
        for i, uid in enumerate(users):
            try:
                if btype == "photo" and msg.photo:
                    await context.bot.send_photo(uid,
                        photo=msg.photo[-1].file_id,
                        caption=msg.caption or "", parse_mode=ParseMode.HTML)
                elif btype == "video" and msg.video:
                    await context.bot.send_video(uid,
                        video=msg.video.file_id,
                        caption=msg.caption or "", parse_mode=ParseMode.HTML)
                else:
                    await context.bot.send_message(uid, msg.text or "",
                                                   parse_mode=ParseMode.HTML)
                ok += 1
            except:
                fail += 1
            if (i + 1) % 20 == 0:
                try: await sm.edit_text(f"📨 Chal raha hai... ({i+1}/{len(users)})")
                except: pass
        await sm.edit_text(
            f"📨 <b>Broadcast Done!</b>\n✅ Sent: {ok}\n❌ Failed: {fail}",
            parse_mode=ParseMode.HTML, reply_markup=back_kb)
        return

    # ── USER SEARCH ──────────────────────────────────
    if awaiting == "search_user":
        try:
            uid = int(msg.text.strip())
            row = db_search_user(uid)
            if row:
                uid_, uname, fname, jdate, blocked, jcount = row
                status = "🚫 Blocked" if blocked else "🟢 Active"
                await msg.reply_text(
                    f"🔍 <b>User Info</b>\n\n"
                    f"🆔 ID         : <code>{uid_}</code>\n"
                    f"👤 Name       : {fname}\n"
                    f"📛 Username   : @{uname or 'nahi'}\n"
                    f"📅 Joined     : {jdate}\n"
                    f"🔢 /start x   : {jcount} baar\n"
                    f"🔴 Status     : {status}",
                    parse_mode=ParseMode.HTML, reply_markup=back_kb)
            else:
                await msg.reply_text("❌ User nahi mila database mein.", reply_markup=back_kb)
        except ValueError:
            await msg.reply_text("❌ Valid User ID dalo (sirf numbers)!", reply_markup=back_kb)
        return

    # ── BLOCK / UNBLOCK ──────────────────────────────
    if awaiting in ("block_user", "unblock_user"):
        try:
            uid = int(msg.text.strip())
            if awaiting == "block_user":
                db_block(uid)
                await msg.reply_text(f"🚫 <code>{uid}</code> block ho gaya!",
                                     parse_mode=ParseMode.HTML, reply_markup=back_kb)
            else:
                db_unblock(uid)
                await msg.reply_text(f"✅ <code>{uid}</code> unblock ho gaya!",
                                     parse_mode=ParseMode.HTML, reply_markup=back_kb)
        except ValueError:
            await msg.reply_text("❌ Valid User ID dalo!", reply_markup=back_kb)
        return

    # ── ADMIN ADD / REMOVE ───────────────────────────
    if awaiting == "add_admin":
        try:
            uid = int(msg.text.strip()); add_admin(uid)
            await msg.reply_text(f"✅ <code>{uid}</code> admin ban gaya!",
                                 parse_mode=ParseMode.HTML, reply_markup=back_kb)
        except ValueError:
            await msg.reply_text("❌ Valid ID dalo!", reply_markup=back_kb)
        return

    if awaiting == "remove_admin":
        try:
            uid = int(msg.text.strip()); remove_admin(uid)
            await msg.reply_text(f"✅ <code>{uid}</code> admin se hata diya!",
                                 parse_mode=ParseMode.HTML, reply_markup=back_kb)
        except ValueError:
            await msg.reply_text("❌ Valid ID dalo!", reply_markup=back_kb)
        return

    # ── CHANNEL ADD — 3 STEP ─────────────────────────
    ch_set_key = context.user_data.get("ch_set_key", "channels")

    if awaiting == "ch_name":
        context.user_data["new_ch_name"] = msg.text.strip()
        context.user_data["awaiting"]    = "ch_id"
        sl = "Set-1" if ch_set_key == "channels" else "Set-2"
        await msg.reply_text(
            f"➕ <b>{sl} — Step 2/3</b>\n\n"
            f"Channel ka <b>ID</b> bhejo\n"
            f"(e.g. <code>-1001234567890</code>)\n\n"
            f"💡 ID kaise pata kare:\n"
            f"Channel ka koi message @userinfobot ko forward karo",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]]))
        return

    if awaiting == "ch_id":
        context.user_data["new_ch_id"] = msg.text.strip()
        context.user_data["awaiting"]  = "ch_link"
        sl = "Set-1" if ch_set_key == "channels" else "Set-2"
        await msg.reply_text(
            f"➕ <b>{sl} — Step 3/3</b>\n\n"
            f"Channel ka <b>Invite Link</b> bhejo\n"
            f"(e.g. <code>https://t.me/yourchannel</code>)",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="admin_panel")]]))
        return

    if awaiting == "ch_link":
        ch_name  = context.user_data.pop("new_ch_name", "Channel")
        ch_id    = context.user_data.pop("new_ch_id", "")
        ch_link  = msg.text.strip()
        key      = context.user_data.pop("ch_set_key", "channels")
        channels = get_channels(key)
        channels.append({"name": ch_name, "id": ch_id, "link": ch_link})
        set_channels(channels, key)
        sl = "Set-1 (Force Join)" if key == "channels" else "Set-2 (After Join)"
        await msg.reply_text(
            f"✅ <b>Channel Add Ho Gaya!</b>\n\n"
            f"📢 Naam   : <b>{ch_name}</b>\n"
            f"🆔 ID     : <code>{ch_id}</code>\n"
            f"🔗 Link   : {ch_link}\n\n"
            f"📌 <b>Button pe yahi naam dikhega: {ch_name}</b>\n"
            f"Total {sl}: <b>{len(channels)}</b>",
            parse_mode=ParseMode.HTML, reply_markup=back_kb)
        return

    # ── JOIN BUTTON CUSTOM PREFIX ────────────────────
    if awaiting == "join_btn_prefix":
        cfg_set("join_btn_style", "custom")
        cfg_set("join_btn_prefix", msg.text.strip())
        await msg.reply_text(
            f"✅ Custom prefix set!\nButton dikhega: <code>{msg.text.strip()} Channel Naam</code>",
            parse_mode=ParseMode.HTML, reply_markup=back_kb)
        return

    # ── SIMPLE CONFIG KEYS ───────────────────────────
    key_map = {
        "deposit_link":     "deposit_link",
        "deposit_text":     "deposit_text",
        "welcome_text":     "welcome_text",
        "joined_text":      "joined_text",
        "btn_verify_label": "btn_verify_label",
        "btn_deposit_label":"btn_deposit_label",
        "alert_not_joined": "alert_not_joined",
        "alert_blocked":    "alert_blocked",
    }
    if awaiting in key_map:
        cfg_set(key_map[awaiting], msg.text.strip())
        label = awaiting.replace("_", " ").title()
        await msg.reply_text(
            f"✅ <b>{label}</b> update ho gaya!",
            parse_mode=ParseMode.HTML, reply_markup=back_kb)

# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

async def run_bot():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN set nahi hai! .env mein BOT_TOKEN lagao.")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CallbackQueryHandler(cb_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, msg_handler))
    logger.info("✅ Ultra Premium Bot v3.0 chal raha hai...")
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
