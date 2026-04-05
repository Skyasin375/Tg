import logging
import asyncio
import sqlite3
import urllib.parse
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ⚙️ CONFIGURATION – UPDATE THESE VALUES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOT_TOKEN = '8665032004:AAFkNcu468fqF6R-2P-XEnHYdTMkJb8vxnk'  # <--- REPLACE WITH YOUR BOT TOKEN
OWNER_ID = 8020955980              # <--- YOUR TELEGRAM ID
OWNER_USERNAME = "zyroxx001"       # Owner username for contact
DEFAULT_UPI = "skbapon353@ybl"
REFERRAL_BONUS = 2                 # ₹2 per referral
DB_FILE = 'guild_glory.db'

# Setup Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🗄️ DATABASE INITIALIZATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, balance INTEGER DEFAULT 0,
            total_added INTEGER DEFAULT 0, spent INTEGER DEFAULT 0, referrals INTEGER DEFAULT 0,
            referrer_id INTEGER, join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            
        c.execute('''CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, credits INTEGER, price INTEGER)''')
            
        c.execute('''CREATE TABLE IF NOT EXISTS coupons (
            id INTEGER PRIMARY KEY AUTOINCREMENT, package_id INTEGER, code TEXT UNIQUE,
            is_used INTEGER DEFAULT 0, used_by INTEGER, used_date TIMESTAMP)''')
            
        c.execute('''CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, utr TEXT UNIQUE,
            screenshot_id TEXT, status TEXT DEFAULT 'pending', date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            
        c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('upi_id', ?)", (DEFAULT_UPI,))
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('website_link', 'https://example.com/redeem')")
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('maintenance', '0')")
        
        c.execute("SELECT COUNT(*) FROM packages")
        if c.fetchone()[0] == 0:
            c.executemany("INSERT INTO packages (credits, price) VALUES (?, ?)", [(1, 100), (2, 200), (3, 300)])
        conn.commit()

init_db()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🛠️ HELPER FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_setting(key):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = c.fetchone()
        return row[0] if row else None

def update_setting(key, value):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE settings SET value=? WHERE key=?", (str(value), key))
        conn.commit()

def is_owner(user_id):
    return user_id == OWNER_ID

def get_main_menu_text(user, bot_username):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT balance FROM users WHERE user_id=?", (user.id,))
        bal = c.fetchone()
        balance = bal[0] if bal else 0
        
    return f"""╔══════════════════════╗
🎮 <b>Guild Glory Credit Shop</b>
╚══════════════════════╝

👋 Welcome, <b>{user.first_name}</b>
💵 Wallet Balance: <b>₹{balance}</b>

━━━━━━━━━━━━━━━
⚡ Select an option below to continue:"""

def main_menu_keyboard(user_id):
    kb = [
        [InlineKeyboardButton("💳 Buy Credit", callback_data="buy_credit"), InlineKeyboardButton("➕ Add Balance", callback_data="add_balance")],
        [InlineKeyboardButton("⚡ Balance & Link", callback_data="balance_link"), InlineKeyboardButton("👥 My Referral", callback_data="my_referral")],
        [InlineKeyboardButton("📊 Stats", callback_data="my_stats"), InlineKeyboardButton("📞 Contact Owner", url=f"https://t.me/{OWNER_USERNAME}")]
    ]
    # Admin Panel button only visible to the Owner
    if is_owner(user_id):
        kb.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_menu")])
        
    return InlineKeyboardMarkup(kb)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🚀 USER COMMANDS & MENUS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot_username = context.bot.username
    
    if get_setting('maintenance') == '1' and not is_owner(user.id):
        return await update.message.reply_text("🛠️ <b>Bot is currently under maintenance.</b> Please check back later.", parse_mode="HTML")

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,))
        if not c.fetchone():
            referrer_id = None
            if context.args and context.args[0].isdigit():
                ref_id = int(context.args[0])
                if ref_id != user.id:
                    c.execute("SELECT user_id FROM users WHERE user_id=?", (ref_id,))
                    if c.fetchone():
                        referrer_id = ref_id
                        c.execute("UPDATE users SET balance = balance + ?, referrals = referrals + 1 WHERE user_id=?", (REFERRAL_BONUS, ref_id))
                        try:
                            await context.bot.send_message(chat_id=ref_id, text=f"🎉 <b>New Referral!</b>\nSomeone joined using your link. ₹{REFERRAL_BONUS} added to your wallet!", parse_mode="HTML")
                        except: pass
            
            c.execute("INSERT INTO users (user_id, username, first_name, referrer_id) VALUES (?, ?, ?, ?)",
                      (user.id, user.username, user.first_name, referrer_id))
            conn.commit()

    context.user_data.clear()
    await update.message.reply_text(get_main_menu_text(user, bot_username), reply_markup=main_menu_keyboard(user.id), parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🎛️ INLINE BUTTON HANDLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    data = query.data
    bot_username = context.bot.username
    await query.answer()

    if get_setting('maintenance') == '1' and not is_owner(user.id) and data != "admin_maintenance":
        return await query.edit_message_text("🛠️ <b>Bot is under maintenance.</b>", parse_mode="HTML")

    # ─── NAVIGATION ───
    if data == "main_menu":
        context.user_data.clear()
        try: await query.message.delete()
        except: pass
        await context.bot.send_message(chat_id=user.id, text=get_main_menu_text(user, bot_username), reply_markup=main_menu_keyboard(user.id), parse_mode="HTML")

    # ─── USER FEATURES ───
    elif data == "balance_link":
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT balance FROM users WHERE user_id=?", (user.id,))
            balance = c.fetchone()[0]
        text = f"╔══════════════════════╗\n🎮 <b>Guild Glory Credit Shop</b>\n╚══════════════════════╝\n\n👋 Welcome, <b>{user.first_name}</b>\n💵 Wallet Balance: <b>₹{balance}</b>\n\n🔗 <b>Referral Link:</b>\nhttps://t.me/{bot_username}?start={user.id}"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]), parse_mode="HTML")

    elif data == "my_referral":
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT referrals FROM users WHERE user_id=?", (user.id,))
            refs = c.fetchone()[0]
        text = f"👥 <b>Referral System</b>\n━━━━━━━━━━━━━━━\n👥 <b>Your Referrals</b>\nTotal Referrals: <b>{refs}</b>\n\n💰 <b>₹{REFERRAL_BONUS} per referral</b>\n<i>Added directly to your wallet</i>\n\n⚠️ <i>Rules:</i>\n• Count ONLY when user joins via referral link\n• Prevent self-referral\n• Prevent duplicate only\n━━━━━━━━━━━━━━━"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]), parse_mode="HTML")

    elif data == "my_stats":
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT balance, total_added, spent, referrals, join_date FROM users WHERE user_id=?", (user.id,))
            bal, added, spent, refs, join = c.fetchone()
            c.execute("SELECT COUNT(*) FROM coupons WHERE used_by=?", (user.id,))
            orders = c.fetchone()[0]
            c.execute("SELECT SUM(p.credits) FROM coupons c JOIN packages p ON c.package_id = p.id WHERE c.used_by=?", (user.id,))
            total_credits = c.fetchone()[0] or 0
        
        join_str = join[:10] if join else "Unknown"
        text = f"📊 <b>Your Statistics</b>\n━━━━━━━━━━━━━━━\n💵 Current Balance: <b>₹{bal}</b>\n💰 Total Topped Up: <b>₹{added}</b>\n🛍 Total Spent: <b>₹{spent}</b>\n👥 Total Referrals: <b>{refs}</b>\n\n🎫 Purchases Made: <b>{orders}</b>\n⭐ Total Credits Bought: <b>{total_credits}</b>\n📅 Joined: <b>{join_str}</b>\n━━━━━━━━━━━━━━━"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]), parse_mode="HTML")

    elif data == "add_balance":
        context.user_data['state'] = 'WAITING_AMOUNT'
        text = "➕ <b>Add Balance</b>\n━━━━━━━━━━━━━━━\n💬 Please send the <b>amount</b> you want to add to your wallet.\n\n<i>(Minimum amount: ₹10)</i>\n<i>(Type /cancel to cancel)</i>"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="main_menu")]]), parse_mode="HTML")

    elif data == "buy_credit":
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT id, credits, price FROM packages ORDER BY credits ASC")
            packages = c.fetchall()
            
            if not packages:
                return await query.edit_message_text("❌ No packages available right now.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]))
            
            text = "💳 <b>Buy Credits (COUPON SYSTEM)</b>\n━━━━━━━━━━━━━━━\nSelect a package below:\n\n"
            kb = []
            for pid, creds, price in packages:
                c.execute("SELECT COUNT(*) FROM coupons WHERE package_id=? AND is_used=0", (pid,))
                stock = c.fetchone()[0]
                status = "✅" if stock > 0 else "❌ Out of stock"
                text += f"⭐ <b>{creds} Credit</b> = ₹{price} ({status})\n"
                if stock > 0:
                    kb.append([InlineKeyboardButton(f"🛒 Buy {creds} Credit (₹{price})", callback_data=f"buy_pkg_{pid}")])
                    
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

    elif data.startswith("buy_pkg_"):
        pkg_id = int(data.split('_')[2])
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT credits, price FROM packages WHERE id=?", (pkg_id,))
            pkg = c.fetchone()
            if not pkg: return await query.answer("Package not found!", show_alert=True)
            creds, price = pkg
            
            c.execute("SELECT balance FROM users WHERE user_id=?", (user.id,))
            balance = c.fetchone()[0]
            
            if balance < price:
                return await query.answer(f"❌ Insufficient Balance! You need ₹{price}.", show_alert=True)
                
            c.execute("SELECT id, code FROM coupons WHERE package_id=? AND is_used=0 ORDER BY RANDOM() LIMIT 1", (pkg_id,))
            coupon = c.fetchone()
            
            if not coupon:
                return await query.answer("❌ Out of stock!", show_alert=True)
                
            coupon_id, coupon_code = coupon
            website = get_setting('website_link')
            
            c.execute("UPDATE users SET balance = balance - ?, spent = spent + ? WHERE user_id=?", (price, price, user.id))
            c.execute("UPDATE coupons SET is_used=1, used_by=?, used_date=CURRENT_TIMESTAMP WHERE id=?", (user.id, coupon_id))
            conn.commit()

        success_msg = f"🎉 <b>Purchase Successful!</b>\n━━━━━━━━━━━━━━━\n🎮 <b>Guild Glory Shop</b>\n━━━━━━━━━━━━━━━\n🎟 <b>Your Coupon Code:</b>\n<code>{coupon_code}</code>\n\n💎 <b>Credits:</b> {creds}\n🌐 <b>Redeem Here:</b>\n{website}\n━━━━━━━━━━━━━━━\n⚠️ <i>IMPORTANT:</i>\n• One purchase = ONE coupon only.\n• Do not share this code."
        await query.edit_message_text(success_msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]]), parse_mode="HTML")

    # ─── ADMIN FEATURES ───
    elif data == "admin_menu":
        if not is_owner(user.id): return await query.answer("❌ Access Denied!", show_alert=True)
        context.user_data.clear()
        
        # Display Maintenance status dynamically
        m_status = "🔴 ON" if get_setting('maintenance') == '1' else "🟢 OFF"
        
        text = f"👑 <b>Admin Panel</b>\n━━━━━━━━━━━━━━━\n🛠️ Maintenance Mode: <b>{m_status}</b>\n\nManage your bot settings below:"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Add Packages", callback_data="admin_add_pkg"), InlineKeyboardButton("🎟 Add Coupons", callback_data="admin_add_coupon")],
            [InlineKeyboardButton("📝 Check Orders", callback_data="admin_orders"), InlineKeyboardButton("📊 Status Dashboard", callback_data="admin_stats")],
            [InlineKeyboardButton("🔗 Set Website URL", callback_data="admin_set_web"), InlineKeyboardButton("🏦 Set UPI ID", callback_data="admin_set_upi")],
            [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"), InlineKeyboardButton("🛠 Maintenance Toggle", callback_data="admin_maintenance")],
            [InlineKeyboardButton("🔙 Exit Admin", callback_data="main_menu")]
        ])
        try: await query.message.delete()
        except: pass
        await context.bot.send_message(chat_id=user.id, text=text, reply_markup=kb, parse_mode="HTML")

    elif data == "admin_stats":
        if not is_owner(user.id): return
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            tot_users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM coupons")
            tot_coupons = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM coupons WHERE is_used=1")
            used_coupons = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM orders WHERE status='pending'")
            pending_orders = c.fetchone()[0]
            c.execute("SELECT SUM(total_added) FROM users")
            revenue = c.fetchone()[0] or 0

        text = f"📊 <b>Admin Status Dashboard</b>\n━━━━━━━━━━━━━━━\n👥 Total Users: <b>{tot_users}</b>\n🎟 Total Coupons: <b>{tot_coupons}</b>\n🎫 Used Coupons: <b>{used_coupons}</b>\n🛒 Unused Coupons: <b>{tot_coupons - used_coupons}</b>\n⏳ Pending Orders: <b>{pending_orders}</b>\n💰 Total Revenue: <b>₹{revenue}</b>\n━━━━━━━━━━━━━━━"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_menu")]]), parse_mode="HTML")

    elif data == "admin_maintenance":
        if not is_owner(user.id): return
        current = get_setting('maintenance')
        new_val = '0' if current == '1' else '1'
        update_setting('maintenance', new_val)
        
        status_word = "🔴 ON (Active)" if new_val == '1' else "🟢 OFF (Disabled)"
        
        # Alert pop-up
        await query.answer(f"Maintenance mode is now {status_word}", show_alert=True)
        
        # Send Explicit Notification to Owner
        await context.bot.send_message(
            chat_id=OWNER_ID, 
            text=f"🛠️ <b>Maintenance Mode Update</b>\n━━━━━━━━━━━━━━━\nThe bot maintenance mode has been turned <b>{status_word}</b>.", 
            parse_mode="HTML"
        )
        
        # Refresh the admin menu to show updated status
        query.data = "admin_menu"
        await button_handler(update, context)

    elif data == "admin_set_web":
        if not is_owner(user.id): return
        context.user_data['state'] = 'WAITING_WEBSITE_LINK'
        current = get_setting('website_link')
        text = f"🔗 <b>Set Website Link</b>\n━━━━━━━━━━━━━━━\nCurrent: <code>{current}</code>\n\n💬 Send the new website URL:"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_menu")]]), parse_mode="HTML")

    elif data == "admin_set_upi":
        if not is_owner(user.id): return
        context.user_data['state'] = 'WAITING_UPI'
        current = get_setting('upi_id')
        text = f"🏦 <b>Set UPI ID</b>\n━━━━━━━━━━━━━━━\nCurrent: <code>{current}</code>\n\n💬 Send the new UPI ID:"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_menu")]]), parse_mode="HTML")

    elif data == "admin_add_pkg":
        if not is_owner(user.id): return
        context.user_data['state'] = 'WAITING_PACKAGE_CREDITS'
        text = "📦 <b>Add New Package</b>\n━━━━━━━━━━━━━━━\n💬 How many <b>Credits</b> is this package for?\n(Send a number, e.g., 4)"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_menu")]]), parse_mode="HTML")

    elif data == "admin_add_coupon":
        if not is_owner(user.id): return
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT id, credits FROM packages ORDER BY credits ASC")
            packages = c.fetchall()
            
        if not packages:
            return await query.answer("Please add a package first!", show_alert=True)
            
        text = "🎟 <b>Add Coupons</b>\n━━━━━━━━━━━━━━━\nSelect which package you want to add coupons for:"
        kb = []
        for pid, creds in packages:
            kb.append([InlineKeyboardButton(f"Add for {creds} Credit Package", callback_data=f"select_pkg_coup_{pid}")])
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_menu")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

    elif data.startswith("select_pkg_coup_"):
        if not is_owner(user.id): return
        pkg_id = int(data.split('_')[3])
        context.user_data['state'] = 'WAITING_COUPON_CODE'
        context.user_data['selected_pkg_id'] = pkg_id
        text = "🎟 <b>Add Coupons</b>\n━━━━━━━━━━━━━━━\n💬 Send the <b>Coupon Code</b>.\n<i>(Send them one by one. I will save each one.)</i>"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Done / Stop", callback_data="admin_menu")]]), parse_mode="HTML")

    elif data == "admin_broadcast":
        if not is_owner(user.id): return
        context.user_data['state'] = 'WAITING_BROADCAST'
        text = "📢 <b>Broadcast Message</b>\n━━━━━━━━━━━━━━━\n💬 Send the message (Text/Photo/Video) to broadcast to all users:"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_menu")]]), parse_mode="HTML")

    elif data == "admin_orders":
        if not is_owner(user.id): return
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT id, user_id, amount, utr, screenshot_id FROM orders WHERE status='pending' LIMIT 1")
            order = c.fetchone()
            
        if not order:
            try: await query.message.delete()
            except: pass
            return await context.bot.send_message(user.id, "✅ No pending orders currently.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_menu")]]))
        
        oid, o_user_id, amount, utr, ss_id = order
        text = f"📝 <b>Pending Order #{oid}</b>\n━━━━━━━━━━━━━━━\n👤 User ID: <code>{o_user_id}</code>\n💵 Amount: ₹{amount}\n🧾 UTR: <code>{utr}</code>"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_ord_{oid}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject_ord_{oid}")],
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin_menu")]
        ])
        
        try: await query.message.delete()
        except: pass
        await context.bot.send_photo(chat_id=user.id, photo=ss_id, caption=text, reply_markup=kb, parse_mode="HTML")

    elif data.startswith("approve_ord_"):
        if not is_owner(user.id): return
        oid = int(data.split('_')[2])
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT user_id, amount FROM orders WHERE id=? AND status='pending'", (oid,))
            order = c.fetchone()
            if order:
                o_user_id, amount = order
                c.execute("UPDATE orders SET status='approved' WHERE id=?", (oid,))
                c.execute("UPDATE users SET balance = balance + ?, total_added = total_added + ? WHERE user_id=?", (amount, amount, o_user_id))
                conn.commit()
                await query.answer("✅ Order Approved & Balance Added!", show_alert=True)
                try: await context.bot.send_message(chat_id=o_user_id, text=f"✅ <b>Payment Approved!</b>\n₹{amount} has been added to your wallet.", parse_mode="HTML")
                except: pass
        # Fetch next order by triggering admin_orders logic
        query.data = "admin_orders"
        await button_handler(update, context)

    elif data.startswith("reject_ord_"):
        if not is_owner(user.id): return
        oid = int(data.split('_')[2])
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT user_id, amount FROM orders WHERE id=? AND status='pending'", (oid,))
            order = c.fetchone()
            if order:
                o_user_id, amount = order
                c.execute("UPDATE orders SET status='rejected' WHERE id=?", (oid,))
                conn.commit()
                await query.answer("❌ Order Rejected!", show_alert=True)
                try: await context.bot.send_message(chat_id=o_user_id, text=f"❌ <b>Payment Rejected!</b>\nYour request for ₹{amount} was rejected. Contact support if this is an error.", parse_mode="HTML")
                except: pass
        # Fetch next order
        query.data = "admin_orders"
        await button_handler(update, context)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📩 MESSAGE HANDLER (STATE MACHINE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private': return
    user = update.effective_user
    text = update.message.text
    state = context.user_data.get('state')

    if text == "/cancel":
        context.user_data.clear()
        return await update.message.reply_text("✅ Action cancelled. Use the menu.", reply_markup=main_menu_keyboard(user.id), parse_mode="HTML")
        
    if text == "/admin" and is_owner(user.id):
        return await button_handler(Update(update.update_id, callback_query=type('obj', (object,), {'data': 'admin_menu', 'answer': lambda *a, **k: asyncio.Future().set_result(None), 'edit_message_text': update.message.reply_text})), context)

    if not state:
        return # Ignore random messages if no state

    # ─── USER STATES ───
    if state == 'WAITING_AMOUNT':
        try:
            amount = int(text)
            if amount < 10:
                return await update.message.reply_text("❌ Minimum amount is ₹10. Try again or /cancel.")
        except:
            return await update.message.reply_text("❌ Invalid amount. Send a number or /cancel.")
            
        context.user_data['add_amount'] = amount
        context.user_data['state'] = 'WAITING_SCREENSHOT'
        upi_id = get_setting('upi_id')
        
        # Generate custom QR
        upi_uri = f"upi://pay?pa={upi_id}&pn=GuildGlory&am={amount}&cu=INR"
        qr_url = f"https://quickchart.io/qr?text={urllib.parse.quote(upi_uri)}&size=400"
        
        msg = f"""
🏦 <b>Payment Processing</b>
━━━━━━━━━━━━━━━
💵 Amount to pay: <b>₹{amount}</b>
💳 UPI ID: <code>{upi_id}</code>

📸 <b>Instruction:</b>
1. Scan the QR code or pay to the UPI ID above.
2. Send the <b>Screenshot</b> of successful payment here.
*(Type /cancel to abort)*
"""
        await update.message.reply_photo(photo=qr_url, caption=msg, parse_mode="HTML")

    elif state == 'WAITING_SCREENSHOT':
        if not update.message.photo:
            return await update.message.reply_text("📸 Please send a <b>photo</b> (screenshot) of the payment, or /cancel.")
        
        context.user_data['screenshot_id'] = update.message.photo[-1].file_id
        context.user_data['state'] = 'WAITING_UTR'
        await update.message.reply_text("📝 Screenshot received! Now send the <b>12-digit UTR / Reference Number</b>.\n*(Type /cancel to abort)*", parse_mode="HTML")

    elif state == 'WAITING_UTR':
        if not text or len(text) < 6:
            return await update.message.reply_text("❌ Invalid UTR. Please send the correct Reference number.")
            
        amount = context.user_data['add_amount']
        ss_id = context.user_data['screenshot_id']
        
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            try:
                c.execute("INSERT INTO orders (user_id, amount, utr, screenshot_id) VALUES (?, ?, ?, ?)",
                          (user.id, amount, text, ss_id))
                conn.commit()
            except sqlite3.IntegrityError:
                return await update.message.reply_text("❌ This UTR has already been submitted!")
                
        context.user_data.clear()
        await update.message.reply_text("✅ <b>Verification Pending!</b>\nYour payment has been sent to the admin. Balance will be added once verified.", parse_mode="HTML", reply_markup=main_menu_keyboard(user.id))
        
        # Notify Admin
        admin_msg = f"📥 <b>New Payment Received!</b>\n👤 User: <code>{user.id}</code>\n💵 Amount: ₹{amount}\n🧾 UTR: <code>{text}</code>"
        try:
            await context.bot.send_photo(chat_id=OWNER_ID, photo=ss_id, caption=admin_msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔍 Check Orders", callback_data="admin_orders")]]))
        except: pass

    # ─── ADMIN STATES ───
    elif state == 'WAITING_WEBSITE_LINK':
        update_setting('website_link', text)
        context.user_data.clear()
        await update.message.reply_text(f"✅ Website link updated to: <code>{text}</code>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_menu")]]))

    elif state == 'WAITING_UPI':
        update_setting('upi_id', text)
        context.user_data.clear()
        await update.message.reply_text(f"✅ UPI ID updated to: <code>{text}</code>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_menu")]]))

    elif state == 'WAITING_PACKAGE_CREDITS':
        try: creds = int(text)
        except: return await update.message.reply_text("❌ Invalid number. Try again.")
        context.user_data['pkg_creds'] = creds
        context.user_data['state'] = 'WAITING_PACKAGE_PRICE'
        await update.message.reply_text(f"📦 Adding {creds} Credit Package.\n💬 Now send the <b>Price</b> in ₹ (e.g., 400):")

    elif state == 'WAITING_PACKAGE_PRICE':
        try: price = int(text)
        except: return await update.message.reply_text("❌ Invalid number. Try again.")
        creds = context.user_data['pkg_creds']
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO packages (credits, price) VALUES (?, ?)", (creds, price))
            conn.commit()
        context.user_data.clear()
        await update.message.reply_text(f"✅ Created Package: <b>{creds} Credit for ₹{price}</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_menu")]]))

    elif state == 'WAITING_COUPON_CODE':
        pkg_id = context.user_data['selected_pkg_id']
        code = text.strip()
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            try:
                c.execute("INSERT INTO coupons (package_id, code) VALUES (?, ?)", (pkg_id, code))
                conn.commit()
                await update.message.reply_text(f"✅ Added coupon <code>{code}</code>.\n\nSend another code to keep adding, or click Done.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Done", callback_data="admin_menu")]]))
            except sqlite3.IntegrityError:
                await update.message.reply_text("❌ This coupon code already exists! Send a different one.")

    elif state == 'WAITING_BROADCAST':
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT user_id FROM users")
            users = [row[0] for row in c.fetchall()]
            
        success, failed = 0, 0
        msg = await update.message.reply_text("📢 Sending broadcast...")
        
        for uid in set(users):
            try:
                await update.message.copy(chat_id=uid)
                success += 1
                await asyncio.sleep(0.05)
            except:
                failed += 1
                
        context.user_data.clear()
        await msg.edit_text(f"✅ <b>Broadcast Complete!</b>\n📨 Sent: {success}\n❌ Failed: {failed}", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_menu")]]))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🚀 MAIN APP EXECUTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    
    print("🤖 Bot is starting...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    # Keep running
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped.")