import logging
import random
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

# ==================== تنظیمات ====================
TOKEN = "8724613423:AAHMrCBnHfbA9TDy7cNtFmDhZQV4V_rLs40"  # توکن جدیدت رو اینجا بذار
OWNER_ID = 8813403561  # آیدی خودت رو اینجا بذار

logging.basicConfig(level=logging.INFO)

GRID_ROWS = 4
GRID_COLS = 5
TOTAL_CELLS = GRID_ROWS * GRID_COLS
NUM_BOMBS = 5
NUM_SAFE = TOTAL_CELLS - NUM_BOMBS
MIN_BET = 1
USERS_FILE = "users.json"

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def get_user(user_id):
    users = load_users()
    user_id_str = str(user_id)
    if user_id_str not in users:
        users[user_id_str] = {"coins": 0}
        save_users(users)
    return users[user_id_str]

def update_user_coins(user_id, amount):
    users = load_users()
    user_id_str = str(user_id)
    if user_id_str not in users:
        users[user_id_str] = {"coins": 0}
    users[user_id_str]["coins"] += amount
    save_users(users)

def get_multiplier(n):
    multipliers = [1.0, 1.05, 1.1, 1.2, 1.5, 1.6, 2.0, 2.7, 3.6, 4.8, 7.0]
    if n < len(multipliers):
        return multipliers[n]
    return 7.0

def build_game_keyboard(game_data, game_over=False):
    bombs = game_data["bombs"]
    revealed = game_data["revealed"]
    bet = game_data["bet"]
    safe_count = len(revealed)
    current_multiplier = get_multiplier(safe_count)
    next_multiplier = get_multiplier(safe_count + 1)
    
    keyboard = []
    for row in range(GRID_ROWS):
        row_buttons = []
        for col in range(GRID_COLS):
            cell_id = row * GRID_COLS + col
            if game_over:
                if cell_id in bombs:
                    text = "💣"
                elif cell_id in revealed:
                    text = "✅"
                else:
                    text = "⬛"
                row_buttons.append(InlineKeyboardButton(text, callback_data="ignore"))
            else:
                if cell_id in revealed:
                    row_buttons.append(InlineKeyboardButton("✅", callback_data="ignore"))
                else:
                    row_buttons.append(InlineKeyboardButton("❓", callback_data=f"open_{cell_id}"))
        keyboard.append(row_buttons)

    if not game_over:
        cashout_amount = bet * current_multiplier
        keyboard.append([InlineKeyboardButton(f"💰 برداشت {cashout_amount:.2f}", callback_data="cashout")])
        keyboard.append([InlineKeyboardButton(f"⏩ بعدی {next_multiplier:.2f}", callback_data="next_show")])
    else:
        keyboard.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu")])
    
    return InlineKeyboardMarkup(keyboard)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    coins = get_user(user_id)["coins"]
    
    text = (
        "🌹 **خوش اومدید به بمب هاب**\n"
        "ریسک از شما، سود از ما ✅\n\n"
        f"💰 موجودی شما: {coins} کوین\n"
        "برای شروع بازی، دکمه زیر را بزنید:"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("💰 ماینز", callback_data="start_game")]])
    
    if query:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    coins = get_user(user_id)["coins"]
    
    if coins < MIN_BET:
        await query.edit_message_text(
            f"❌ شما کوین لازم برای بازی رو ندارید.\nحداقل شرط {MIN_BET} کوین است.\nموجودی شما: {coins} کوین",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu")]]),
            parse_mode="Markdown"
        )
        return
    
    context.user_data["state"] = "WAITING_BET"
    await query.edit_message_text(
        f"💰 مبلغ بازی رو انتخاب کنید 🛑\nحداقل مبلغ {MIN_BET} کوین 💲\nموجودی شما: {coins} کوین\n\nلطفاً یک عدد وارد کنید:",
        parse_mode="Markdown"
    )

async def handle_bet_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != "WAITING_BET":
        return
    
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not text.isdigit():
        await update.message.reply_text("❌ لطفاً فقط یک عدد وارد کنید.")
        return
    
    bet_amount = int(text)
    if bet_amount < MIN_BET:
        await update.message.reply_text(f"❌ حداقل مبلغ {MIN_BET} کوین است.")
        return
    
    user_data = get_user(user_id)
    if user_data["coins"] < bet_amount:
        await update.message.reply_text(
            f"❌ موجودی شما کافی نیست.\nموجودی: {user_data['coins']} کوین",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu")]])
        )
        return
    
    update_user_coins(user_id, -bet_amount)
    
    bomb_positions = set(random.sample(range(TOTAL_CELLS), NUM_BOMBS))
    game_data = {
        "bombs": bomb_positions,
        "revealed": set(),
        "bet": bet_amount,
        "game_over": False
    }
    context.user_data["game"] = game_data
    context.user_data["state"] = "PLAYING"
    
    text = (
        f"💣 **بازی شروع شد!**\n"
        f"💰 شرط: {bet_amount} کوین\n"
        f"⭐ ضریب فعلی: {get_multiplier(0):.2f}\n"
        f"🎯 {NUM_SAFE} خانه امن پیدا کن!\n\n"
        "روی ❓ کلیک کن."
    )
    keyboard = build_game_keyboard(game_data)
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def handle_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if data == "main_menu":
        await main_menu(update, context)
        return
    
    if data == "start_game":
        await start_game(update, context)
        return
    
    if data in ["ignore", "next_show"]:
        return
    
    game_data = context.user_data.get("game")
    if not game_data or game_data.get("game_over"):
        await query.edit_message_text("⏳ بازی تمام شده.")
        return
    
    if data == "cashout":
        safe_count = len(game_data["revealed"])
        multiplier = get_multiplier(safe_count)
        cashout_amount = game_data["bet"] * multiplier
        update_user_coins(user_id, cashout_amount)
        game_data["game_over"] = True
        text = (
            f"💰 **برداشت موفق!**\n"
            f"ضریب: {multiplier:.2f}\n"
            f"مبلغ: {cashout_amount:.2f} کوین\n"
            f"موجودی جدید: {get_user(user_id)['coins']} کوین"
        )
        keyboard = build_game_keyboard(game_data, game_over=True)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        return
    
    if data.startswith("open_"):
        cell_id = int(data.split("_")[1])
        bombs = game_data["bombs"]
        revealed = game_data["revealed"]
        
        if cell_id in revealed:
            return
        
        if cell_id in bombs:
            game_data["game_over"] = True
            text = f"💥 **باختی!**\nمبلغ شرط: {game_data['bet']} کوین از دست رفت."
            keyboard = build_game_keyboard(game_data, game_over=True)
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
            return
        
        revealed.add(cell_id)
        safe_count = len(revealed)
        
        if safe_count == NUM_SAFE:
            game_data["game_over"] = True
            multiplier = get_multiplier(safe_count)
            win_amount = game_data["bet"] * multiplier
            update_user_coins(user_id, win_amount)
            text = (
                f"🎉 **تبریک! برنده شدی!**\n"
                f"ضریب: {multiplier:.2f}\n"
                f"جایزه: {win_amount:.2f} کوین\n"
                f"موجودی جدید: {get_user(user_id)['coins']} کوین"
            )
            keyboard = build_game_keyboard(game_data, game_over=True)
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
            return
        
        current_multiplier = get_multiplier(safe_count)
        next_multiplier = get_multiplier(safe_count + 1)
        cashout_amount = game_data["bet"] * current_multiplier
        
        text = (
            f"💣 **بازی ادامه دارد**\n"
            f"⭐ ضریب فعلی: {current_multiplier:.2f}\n"
            f"⏩ ضریب بعدی: {next_multiplier:.2f}\n"
            f"🎯 {NUM_SAFE - safe_count} خانه باقی‌مانده\n"
            f"💰 قابل برداشت: {cashout_amount:.2f} کوین"
        )
        keyboard = build_game_keyboard(game_data)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ شما دسترسی ندارید.")
        return
    
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("❌ فرمت: /addcoins [تعداد] [آیدی]")
        return
    
    try:
        amount = int(args[0])
        target_id = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ اعداد معتبر وارد کنید.")
        return
    
    update_user_coins(target_id, amount)
    await update.message.reply_text(f"✅ {amount} کوین به کاربر {target_id} اضافه شد.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await main_menu(update, context)

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addcoins", add_coins))
    app.add_handler(CommandHandler("menu", start))
    
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_game, pattern="^start_game$")],
        states={
            "WAITING_BET": [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bet_input)],
        },
        fallbacks=[CommandHandler("menu", start)],
        allow_reentry=True
    )
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(handle_game_callback, pattern="^(open_|cashout|main_menu|next_show|start_game|ignore)"))
    
    print("🤖 ربات ماین‌یاب با سیستم کوین روشن شد...")
    app.run_polling()

if __name__ == "__main__":
    main()
