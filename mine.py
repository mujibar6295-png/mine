import asyncio
import logging
import sqlite3
import os
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    WebAppInfo,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# Configuration Constants
TOKEN = "8984910379:AAHoZiQey_EEvTKqjugqRphsCIH7J9tqd_A"
ADMIN_ID = 5624448603
WEB_APP_URL = "https://mujibar6295-png.github.io/telegram-ad-app/"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Flask App setup for Render Port Binding
app = Flask(__name__)

@app.route('/')
def home():
    return "AdsMine Bot Server is Running Alive & Active!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Database Setup
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0.0,
            ads_watched INTEGER DEFAULT 0,
            referred_by INTEGER,
            total_referrals INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            chat_id TEXT PRIMARY KEY,
            invite_link TEXT
        )
    ''')
    
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('ads_value', '0.05')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('min_withdraw', '50.0')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('ref_value', '1.0')")
    
    conn.commit()
    conn.close()

init_db()

def get_setting(key):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    val = cursor.fetchone()
    conn.close()
    return val[0] if val else "0"

def update_setting(key, value):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

async def check_forced_subscription(user_id: int) -> bool:
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id FROM channels")
    channels = cursor.fetchall()
    conn.close()

    for (chat_id,) in channels:
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception:
            pass
    return True

async def get_join_keyboard():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, invite_link FROM channels")
    channels = cursor.fetchall()
    conn.close()

    keyboard = []
    for chat_id, link in channels:
        try:
            chat = await bot.get_chat(chat_id)
            name = chat.title or "Join Channel"
            keyboard.append([InlineKeyboardButton(text=f"📢 {name}", url=link)])
        except:
            keyboard.append([InlineKeyboardButton(text="📢 Join Channel", url=link)])
            
    keyboard.append([InlineKeyboardButton(text="🔄 Verify Membership", callback_data="verify_join")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

class SupportStates(StatesGroup):
    waiting_for_message = State()
    admin_reply = State()

class WithdrawStates(StatesGroup):
    waiting_for_upi = State()
    waiting_for_amount = State()

# Reply Keyboard (যেখান থেকে WebApp ওপেন করলে ডেটা বটের কাছে আসবে)
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📺 Watch Ads & Earn", web_app=WebAppInfo(url=WEB_APP_URL))],
            [KeyboardButton(text="👤 Account"), KeyboardButton(text="💳 Withdraw")],
            [KeyboardButton(text="🤝 Ref & Earn"), KeyboardButton(text="📞 Support")]
        ],
        resize_keyboard=True
    )

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    args = message.text.split()
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,))
    existing = cursor.fetchone()
    
    referrer_id = None
    if not existing:
        if len(args) > 1 and args[1].isdigit():
            ref_id = int(args[1])
            if ref_id != user_id:
                cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (ref_id,))
                if cursor.fetchone():
                    referrer_id = ref_id
                    
        cursor.execute("INSERT INTO users (user_id, username, referred_by) VALUES (?, ?, ?)", 
                       (user_id, username, referrer_id))
        conn.commit()
    conn.close()

    if not await check_forced_subscription(user_id):
        kb = await get_join_keyboard()
        await message.answer("⚠️ **Access Denied!**\n\nYou must join our official channels/groups below to use this bot.", reply_markup=kb, parse_mode="Markdown")
        return

    welcome_msg = (
        f"👋 Welcome to **AdsMine Bot**, {username}!\n\n"
        f"Your ultimate platform to earn rewards by watching short ads, completing referrals, and more.\n\n"
        f"👇 **Choose an option from the keyboard menu below:**"
    )
    await message.answer(welcome_msg, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "verify_join")
async def verify_join_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if await check_forced_subscription(user_id):
        await callback.message.delete()
        
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT referred_by FROM users WHERE user_id = ? AND total_referrals = 0", (user_id,))
        row = cursor.fetchone()
        if row and row[0]:
            ref_id = row[0]
            ref_bonus = float(get_setting("ref_value"))
            
            cursor.execute("UPDATE users SET balance = balance + ?, total_referrals = total_referrals + 1 WHERE user_id = ?", (ref_bonus, ref_id))
            conn.commit()
            
            try:
                await bot.send_message(
                    ref_id, 
                    f"🎉 **New Referral Joined!**\n\nUser @{callback.from_user.username or user_id} joined via your link and verified membership.\nBonus added: ₹{ref_bonus}",
                    parse_mode="Markdown"
                )
            except:
                pass
        conn.close()

        await callback.message.answer("✅ **Verification Successful!** Welcome aboard.", reply_markup=get_main_keyboard(), parse_mode="Markdown")
    else:
        await callback.answer("❌ You have not joined all required channels yet!", show_alert=True)

# 👤 Account Button
@dp.message(F.text == "👤 Account")
async def account_menu(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance, ads_watched, total_referrals FROM users WHERE user_id = ?", (user_id,))
    data = cursor.fetchone()
    conn.close()
    
    if data:
        balance, ads_watched, total_refs = data
        text = (
            f"👤 **Your Account Profile**\n\n"
            f"🆔 **User ID:** `{user_id}`\n"
            f"💰 **Balance:** `₹{balance:.2f}`\n"
            f"📺 **Ads Watched:** `{ads_watched}`\n"
            f"👥 **Total Referrals:** `{total_refs}`"
        )
        await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

# 🤝 Ref & Earn Button
@dp.message(F.text == "🤝 Ref & Earn")
async def ref_menu(message: types.Message):
    user_id = message.from_user.id
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    ref_value = get_setting("ref_value")
    
    text = (
        f"🤝 **Referral & Earn Program**\n\n"
        f"🎁 **Instant Reward:** Get `₹{ref_value}` when your referred user joins.\n"
        f"🔄 **Lifetime Commission:** Earn **5%** commission on your referrals' activity!\n\n"
        f"🔗 **Your Unique Link:**\n`{ref_link}`"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

# 📞 Support Button
@dp.message(F.text == "📞 Support")
async def support_menu(message: types.Message, state: FSMContext):
    await message.answer(
        "📞 **Customer Support**\n\nPlease type your issue or query below. (Type /cancel to abort)",
        parse_mode="Markdown"
    )
    await state.set_state(SupportStates.waiting_for_message)

@dp.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Action cancelled.", reply_markup=get_main_keyboard())

@dp.message(SupportStates.waiting_for_message)
async def process_support_msg(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    text = message.text
    
    await state.clear()
    
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Reply to User", callback_data=f"reply_user_{user_id}")]
    ])
    
    await bot.send_message(
        ADMIN_ID,
        f"📩 **New Support Message**\n\nFrom: @{username} (`{user_id}`)\nMessage:\n{text}",
        reply_markup=admin_kb,
        parse_mode="Markdown"
    )
    await message.answer("✅ Message sent to support.", reply_markup=get_main_keyboard())

@dp.callback_query(F.data.regexp(r"^reply_user_(\d+)$"))
async def admin_reply_prompt(callback: types.CallbackQuery, state: FSMContext):
    target_user_id = int(callback.data.split("_")[2])
    await state.update_data(target_user=target_user_id)
    await callback.message.answer(f"✍️ Type your reply message for user `{target_user_id}`:", parse_mode="Markdown")
    await state.set_state(SupportStates.admin_reply)

@dp.message(SupportStates.admin_reply)
async def send_admin_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_user = data.get("target_user")
    reply_text = message.text
    await state.clear()
    
    try:
        await bot.send_message(target_user, f"📩 **Admin Reply:**\n\n{reply_text}", parse_mode="Markdown")
        await message.answer("✅ Reply sent successfully.")
    except Exception as e:
        await message.answer(f"❌ Failed to send reply: {e}")

# 💳 Withdraw Button
@dp.message(F.text == "💳 Withdraw")
async def withdraw_menu(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    min_w = float(get_setting("min_withdraw"))
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    balance = row[0] if row else 0.0
    
    if balance < min_w:
        await message.answer(f"❌ Minimum withdrawal amount is ₹{min_w}. Your balance is ₹{balance:.2f}", reply_markup=get_main_keyboard())
        return
        
    await message.answer(
        f"💳 **Withdrawal Section**\n\nYour Balance: `₹{balance:.2f}`\n\nPlease enter your **UPI ID**:",
        parse_mode="Markdown"
    )
    await state.set_state(WithdrawStates.waiting_for_upi)

@dp.message(WithdrawStates.waiting_for_upi)
async def process_withdraw_upi(message: types.Message, state: FSMContext):
    upi_id = message.text.strip()
    await state.update_data(upi_id=upi_id)
    
    user_id = message.from_user.id
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    balance = cursor.fetchone()[0]
    conn.close()
    
    await message.answer(f"💵 Enter amount (Max `₹{balance:.2f}`):", parse_mode="Markdown")
    await state.set_state(WithdrawStates.waiting_for_amount)

@dp.message(WithdrawStates.waiting_for_amount)
async def process_withdraw_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid amount.")
        return
        
    user_id = message.from_user.id
    data = await state.get_data()
    upi_id = data.get("upi_id")
    await state.clear()
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    balance = cursor.fetchone()[0]
    
    min_w = float(get_setting("min_withdraw"))
    if amount < min_w or amount > balance:
        conn.close()
        await message.answer(f"❌ Invalid amount. Must be between ₹{min_w} and ₹{balance:.2f}", reply_markup=get_main_keyboard())
        return
        
    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Paid & Verify", callback_data=f"wd_paid_{user_id}_{amount}"),
         InlineKeyboardButton(text="❌ Reject & Refund", callback_data=f"wd_reject_{user_id}_{amount}")]
    ])
    
    await bot.send_message(
        ADMIN_ID,
        f"🔔 **New Withdrawal Request**\n\nUser ID: `{user_id}`\nUPI: `{upi_id}`\nAmount: `₹{amount}`",
        reply_markup=admin_kb,
        parse_mode="Markdown"
    )
    
    await message.answer("✅ **Request Submitted!**", reply_markup=get_main_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("wd_"))
async def admin_wd_action(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    action = parts[1]
    user_id = int(parts[2])
    amount = float(parts[3])
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    
    if action == "paid":
        conn.close()
        try:
            await bot.send_message(user_id, f"🎉 **Withdrawal Successful!** `₹{amount}` has been paid.", parse_mode="Markdown")
        except:
            pass
        await callback.message.edit_text(callback.message.text + "\n\n**[PAID]**")
    elif action == "reject":
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()
        try:
            await bot.send_message(user_id, f"❌ **Withdrawal Rejected!** `₹{amount}` refunded.", parse_mode="Markdown")
        except:
            pass
        await callback.message.edit_text(callback.message.text + "\n\n**[REJECTED & REFUNDED]**")

# Admin Commands
@dp.message(Command("addchannel"))
async def cmd_addchannel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split(maxsplit=2)
    if len(args) < 3: return
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO channels (chat_id, invite_link) VALUES (?, ?)", (args[1], args[2]))
    conn.commit()
    conn.close()
    await message.reply("✅ Channel added.")

@dp.message(Command("adsvalue"))
async def cmd_adsvalue(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) < 2: return
    update_setting("ads_value", args[1])
    await message.reply(f"✅ Ad reward value updated to `₹{args[1]}`", parse_mode="Markdown")

@dp.message(Command("minwithdraw"))
async def cmd_minwithdraw(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) < 2: return
    update_setting("min_withdraw", args[1])
    await message.reply(f"✅ Minimum withdrawal limit updated to `₹{args[1]}`", parse_mode="Markdown")

@dp.message(Command("refvalue"))
async def cmd_refvalue(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) < 2: return
    update_setting("ref_value", args[1])
    await message.reply(f"✅ Referral bonus updated to `₹{args[1]}`", parse_mode="Markdown")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    text = message.text.replace("/broadcast", "").strip()
    if not text: return
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    count = 0
    for (uid,) in users:
        try:
            await bot.send_message(uid, text, parse_mode="Markdown")
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.reply(f"✅ Broadcast completed to {count} users.")

@dp.message(Command("userlist"))
async def cmd_userlist(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, balance, ads_watched, total_referrals FROM users")
    users = cursor.fetchall()
    conn.close()
    filename = "userlist.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write("UserID | Username | Balance | Ads Watched | Total Referrals\n")
        f.write("-" * 65 + "\n")
        for u in users:
            f.write(f"{u[0]} | @{u[1]} | {u[2]} | {u[3]} | {u[4]}\n")
    await message.reply_document(types.FSInputFile(filename), caption="📊 **Complete User Database Export**", parse_mode="Markdown")

# 🎯 FINAL FIX: Mini App থেকে আসা ডেটা হ্যান্ডলার
@dp.message(F.web_app_data)
async def web_app_data_handler(message: types.Message):
    # আমরা JSON এর বদলে সিম্পল টেক্সট রিসিভ করছি (index.html থেকে)
    data = message.web_app_data.data
    
    if data == "ad_completed_success":
        user_id = message.from_user.id
        ad_reward = float(get_setting("ads_value"))
        
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        
        # User ব্যালেন্স আপডেট
        cursor.execute("UPDATE users SET balance = balance + ?, ads_watched = ads_watched + 1 WHERE user_id = ?", (ad_reward, user_id))
        
        # 5% Referral Commission
        cursor.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row[0]:
            ref_id = row[0]
            commission = ad_reward * 0.05
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (commission, ref_id))
            try:
                await bot.send_message(ref_id, f"💸 **Referral Commission:** You earned `₹{commission:.4f}`.", parse_mode="Markdown")
            except:
                pass
                
        conn.commit()
        conn.close()
        
        # ব্যালেন্স অ্যাড হওয়ার কনফার্মেশন
        await message.reply(f"✅ **Reward Credited!**\n\n+₹{ad_reward:.2f} has been added to your balance.", reply_markup=get_main_keyboard(), parse_mode="Markdown")

async def main():
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
