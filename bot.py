import os
import asyncio
import logging
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web


load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# ═══════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════
BOT_TOKEN         = os.getenv("BOT_TOKEN")
MONGO_URI         = os.getenv("MONGO_URI")

REQUIRED_CHANNELS = ["@bulldrop_n1", "@uzbekroblox", "@trade_chanel_uz"]
TRADE_CHANNEL     = "@trade_chanel_uz"
CARD_NUMBER       = os.getenv("CARD_NUMBER", "5614682091344749")
CARD_OWNER        = os.getenv("CARD_OWNER", "Nurboyev.N")
CHAT_LINK         = os.getenv("CHAT_LINK", "https://t.me/roblox_chat_veko")
ROBLOX_SCRIPT_CHANNEL = os.getenv("ROBLOX_SCRIPT_CHANNEL", "https://t.me/deltauzbrb")

ADMIN_IDS = {8325726426, 8667862086, 8866852203, 7405798326}

def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

ADMIN_ID = 8667862086

# ═══════════════════════════════════════════════════════
# O'YIN KATEGORIYALARI
# ═══════════════════════════════════════════════════════
GAME_CATEGORIES = [
    ("steal_brainrot", "🧠 Steal a Brainrot"),
    ("grow_garden",    "🌱 Grow a Garden"),
    ("escape_tsunami", "🌊 Escape Tsunami"),
    ("mm2",            "🔪 MM2"),
    ("blox_fruit",     "🍎 Blox Fruit"),
    ("escape_keyboard","⌨️ Escape Keyboard"),
]

GAME_LABELS = {k: v for k, v in GAME_CATEGORIES}

# ═══════════════════════════════════════════════════════
# KO'P TIL TIZIMI
# ═══════════════════════════════════════════════════════
LANGS = {
    "uz": {
        "flag": "🇺🇿", "name": "O'zbek tili",
        "start_welcome": "🌟 *Assalomu alaykum, {name}!*\n\n🤖 Bu bot orqali siz:\n🛒 Robux sotib olishingiz,\n📊 O'z buyumlaringizni sotishingiz,\n🔄 Boshqa foydalanuvchilar bilan trade qilishingiz mumkin.\n\n👇 Quyidagi menyudan foydalaning:",
        "choose_lang": "🌐 Tilni tanlang / Choose language / Выберите язык:",
        "btn_buy": "🛒 Robux sotib olish",
        "btn_profile": "👤 Profil",
        "btn_deposit": "💰 Hisob to'ldirish",
        "btn_trades": "🔄 Tradelar",
        "btn_sales": "📊 Sotuvlar",
        "btn_add_trade": "➕ Trade qo'shish",
        "btn_add_sale": "➕ Sotish qo'shish",
        "btn_online": "🌐 Online Traderlar",
        "btn_cart": "🛒 Savat",
        "btn_chat": "💬 Chat",
        "btn_contract": "📜 Shartnoma qilish",
        "btn_ad": "📣 Reklama qilish",
        "btn_admin_service": "🛡 Adminlik xizmati",
        "btn_suggest": "💡 Taklif berish",
        "btn_search": "🔍 Qidiruv",
        "btn_referral": "🎁 Referal",
        "btn_change_lang": "🌐 Tilni o'zgartirish",
        "sub_msg": "👋 Salom! Botdan foydalanish uchun avval quyidagi kanallarga obuna bo'ling!",
        "sub_confirm": "✅ Obunani tasdiqlash",
        "not_subbed": "❌ Hali barcha kanallarga obuna bo'lmagansiz!",
        "muted_msg": "🔇 Siz mute oldingiz! {rem} vaqt qoldi.",
        "no_trades": "🔄 Hozircha faol tradelar yo'q.\n\n➕ *Trade qo'shish* tugmasini bosing!",
        "no_sales": "📊 Hozircha sotuvdagi buyumlar yo'q.\n\n➕ *Sotish qo'shish* tugmasini bosing!",
        "choose_game": "🎮 Qaysi o'yindagi itemingiz?\n\nO'yinni tanlang:",
        "trade_title_prompt": "📦 Trade sarlavhasi yozing:",
        "photo_prompt": "📸 Rasm yuboring (ixtiyoriy):",
        "bio_prompt": "📝 Bio yozing (nima taklif qilyapsiz, nima xohlaysiz) yoki o'tkazib yuboring:",
        "sale_name_prompt": "📦 Nima sotmoqchisiz? Nom yozing:",
        "cancel": "❌ Bekor qilish",
        "skip": "⏭ O'tkazib yuborish",
        "cancelled": "Bekor qilindi.",
        "trade_added": "✅ Trade e'lon qilindi! *#{sid}*",
        "sale_added": "✅ Sotuv e'lon qilindi! *#{sid}*\n📦 {name}\n💰 {price:,} {currency}",
        "new_trade_channel": "🔄 *YANGI TRADE E'LON*\n━━━━━━━━━━━━━━━━━━━━\n\n1️⃣ *Foydalanuvchi:* @{uname}\n\n2️⃣ *Buyum nomi:*\n{item_name}\n\n3️⃣ *Bio:*\n{bio}\n\n4️⃣ 🎮 *O'yin:* {game}\n\n4️⃣ 🔄 *Trade*\n\n━━━━━━━━━━━━━━━━━━━━\n💬 Murojaat: @{uname}",
        "new_sale_channel": "🏷 *YANGI SOTUV E'LON*\n━━━━━━━━━━━━━━━━━━━━\n\n1️⃣ *Foydalanuvchi:* @{uname}\n\n2️⃣ *Buyum nomi:*\n{item_name}\n\n3️⃣ *Bio:*\n{bio}\n\n4️⃣ 🎮 *O'yin:* {game}\n\n5️⃣ 🏷 *Sotiladi* — {price} {currency}\n\n━━━━━━━━━━━━━━━━━━━━\n💬 Murojaat: @{uname}",
        "contact_btn": "💬 Murojaat",
        "prev": "⬅️ Oldingi",
        "next": "➡️ Keyingi",
        "add_cart": "🛒 Savatga solish",
        "trade_label": "🔄 TRADE",
        "sale_label": "🛍 SOTUV",
        "btn_roblox_script": "🎮 Roblox Skript",
        "roblox_script_msg": "🎮 *Roblox skriptlar*\n\nEng so'nggi va ishlaydigan skriptlarni olish uchun pastdagi kanalimizga o'ting:",
        "btn_roblox_script_link": "📂 Skriptlar kanali",
        "btn_scammers": "🚨 Mashkalar",
        "scam_menu_msg": "🚨 *Mashkalar (firibgarlar) bo'limi*\n\nBu yerda firibgarlik qilgan foydalanuvchilar haqida ma'lumot olishingiz mumkin.",
        "btn_scam_view": "👀 Mashkalarni ko'rish",
        "btn_scam_search": "🔍 Qidirish",
        "scam_search_prompt": "🔍 Tekshirmoqchi bo'lgan foydalanuvchining @username sini yozing:",
        "scam_write_username": "✍️ @username yozing:",
        "no_scammers": "🚨 Hozircha mashkalar ro'yxati bo'sh.",
        "scam_not_found": "✅ Bu foydalanuvchi mashkalar ro'yxatida topilmadi.",
        "scam_found_warn": "⚠️ *DIQQAT!* Bu foydalanuvchi mashkalar ro'yxatida bor!",
        "choose_trade_category": "🔄 Qaysi o'yindagi tradelarni ko'rmoqchisiz?\n\nKategoriyani tanlang:",
        "choose_sale_category": "📊 Qaysi o'yindagi sotuvlarni ko'rmoqchisiz?\n\nKategoriyani tanlang:",
        "back_to_categories": "🔙 Kategoriyalar",
        "no_trades_in_cat": "🔄 Bu kategoriyada hozircha tradelar yo'q.",
        "no_sales_in_cat": "📊 Bu kategoriyada hozircha sotuvlar yo'q.",
        "title_min_len": "❌ Sarlavha kamida 5 ta belgi bo'lsin, qaytadan yozing:",
        "trade_updated": "✅ Trade muvaffaqiyatli yangilandi!",
        "sale_updated": "✅ Sotuv muvaffaqiyatli yangilandi!",
        "edit_name_prompt": "✏️ Yangi nomni yozing:",
        "edit_photo_prompt": "📸 Yangi rasm yuboring (o'tkazib yuborish ham mumkin):",
        "edit_bio_prompt": "📝 Yangi bio yozing:",
        "edit_price_prompt": "💰 Yangi narxni kiriting (faqat raqam):",
        "only_number": "❌ Faqat raqam kiriting:",
        "choose_currency": "💱 Valyutani tanlang:",
        "currency_som": "💵 So'm (UZS)",
        "currency_robux": "🪙 Robux",
        "price_prompt": "💰 Narxni yozing ({cur} da):",
        "no_permission": "❌ Sizda ruxsat yo'q!",
    },
    "en": {
        "flag": "🇺🇸", "name": "English",
        "start_welcome": "🌟 *Welcome, {name}!*\n\n🤖 With this bot you can:\n🛒 Buy Robux,\n📊 Sell your items,\n🔄 Trade with other users.\n\n👇 Use the menu below:",
        "choose_lang": "🌐 Tilni tanlang / Choose language / Выберите язык:",
        "btn_buy": "🛒 Buy Robux",
        "btn_profile": "👤 Profile",
        "btn_deposit": "💰 Top up balance",
        "btn_trades": "🔄 Trades",
        "btn_sales": "📊 Sales",
        "btn_add_trade": "➕ Add Trade",
        "btn_add_sale": "➕ Add Sale",
        "btn_online": "🌐 Online Traders",
        "btn_cart": "🛒 Cart",
        "btn_chat": "💬 Chat",
        "btn_contract": "📜 Make Contract",
        "btn_ad": "📣 Advertise",
        "btn_admin_service": "🛡 Admin Service",
        "btn_suggest": "💡 Suggestion",
        "btn_search": "🔍 Search",
        "btn_referral": "🎁 Referral",
        "btn_change_lang": "🌐 Change Language",
        "sub_msg": "👋 Hello! Please subscribe to all channels to use the bot!",
        "sub_confirm": "✅ Confirm Subscription",
        "not_subbed": "❌ You haven't subscribed to all channels yet!",
        "muted_msg": "🔇 You are muted! {rem} remaining.",
        "no_trades": "🔄 No active trades yet.\n\n➕ Press *Add Trade*!",
        "no_sales": "📊 No active sales yet.\n\n➕ Press *Add Sale*!",
        "choose_game": "🎮 Which game is your item from?\n\nSelect a game:",
        "trade_title_prompt": "📦 Write a trade title:",
        "photo_prompt": "📸 Send a photo (optional):",
        "bio_prompt": "📝 Write bio (what you offer, what you want) or skip:",
        "sale_name_prompt": "📦 What do you want to sell? Write a name:",
        "cancel": "❌ Cancel",
        "skip": "⏭ Skip",
        "cancelled": "Cancelled.",
        "trade_added": "✅ Trade posted! *#{sid}*",
        "sale_added": "✅ Sale posted! *#{sid}*\n📦 {name}\n💰 {price:,} {currency}",
        "new_trade_channel": "🔄 *NEW TRADE*\n━━━━━━━━━━━━━━━━━━━━\n\n1️⃣ *User:* @{uname}\n\n2️⃣ *Item:*\n{item_name}\n\n3️⃣ *Bio:*\n{bio}\n\n4️⃣ 🎮 *Game:* {game}\n\n4️⃣ 🔄 *Trade*\n\n━━━━━━━━━━━━━━━━━━━━\n💬 Contact: @{uname}",
        "new_sale_channel": "🏷 *NEW SALE*\n━━━━━━━━━━━━━━━━━━━━\n\n1️⃣ *User:* @{uname}\n\n2️⃣ *Item:*\n{item_name}\n\n3️⃣ *Bio:*\n{bio}\n\n4️⃣ 🎮 *Game:* {game}\n\n5️⃣ 🏷 *For sale* — {price} {currency}\n\n━━━━━━━━━━━━━━━━━━━━\n💬 Contact: @{uname}",
        "contact_btn": "💬 Contact",
        "prev": "⬅️ Prev",
        "next": "➡️ Next",
        "add_cart": "🛒 Add to Cart",
        "trade_label": "🔄 TRADE",
        "sale_label": "🛍 SALE",
        "btn_roblox_script": "🎮 Roblox Script",
        "roblox_script_msg": "🎮 *Roblox Scripts*\n\nTo get the latest working scripts, go to our channel below:",
        "btn_roblox_script_link": "📂 Scripts Channel",
        "btn_scammers": "🚨 Scammers",
        "scam_menu_msg": "🚨 *Scammers section*\n\nHere you can check information about users who have scammed others.",
        "btn_scam_view": "👀 View scammers",
        "btn_scam_search": "🔍 Search",
        "scam_search_prompt": "🔍 Enter the @username of the user you want to check:",
        "scam_write_username": "✍️ Write @username:",
        "no_scammers": "🚨 The scammers list is currently empty.",
        "scam_not_found": "✅ This user was not found in the scammers list.",
        "scam_found_warn": "⚠️ *WARNING!* This user is on the scammers list!",
        "choose_trade_category": "🔄 Which game's trades do you want to see?\n\nChoose a category:",
        "choose_sale_category": "📊 Which game's sales do you want to see?\n\nChoose a category:",
        "back_to_categories": "🔙 Categories",
        "no_trades_in_cat": "🔄 There are no trades in this category yet.",
        "no_sales_in_cat": "📊 There are no sales in this category yet.",
        "title_min_len": "❌ Title must be at least 5 characters, write again:",
        "trade_updated": "✅ Trade updated successfully!",
        "sale_updated": "✅ Sale updated successfully!",
        "edit_name_prompt": "✏️ Write the new name:",
        "edit_photo_prompt": "📸 Send a new photo (you can also skip):",
        "edit_bio_prompt": "📝 Write the new bio:",
        "edit_price_prompt": "💰 Enter the new price (numbers only):",
        "only_number": "❌ Please enter a number:",
        "choose_currency": "💱 Choose currency:",
        "currency_som": "💵 Som (UZS)",
        "currency_robux": "🪙 Robux",
        "price_prompt": "💰 Write the price (in {cur}):",
        "no_permission": "❌ You don't have permission!",
    },
    "ru": {
        "flag": "🇷🇺", "name": "Русский",
        "start_welcome": "🌟 *Добро пожаловать, {name}!*\n\n🤖 С этим ботом вы можете:\n🛒 Покупать Robux,\n📊 Продавать свои предметы,\n🔄 Торговаться с другими пользователями.\n\n👇 Используйте меню ниже:",
        "choose_lang": "🌐 Tilni tanlang / Choose language / Выберите язык:",
        "btn_buy": "🛒 Купить Robux",
        "btn_profile": "👤 Профиль",
        "btn_deposit": "💰 Пополнить баланс",
        "btn_trades": "🔄 Трейды",
        "btn_sales": "📊 Продажи",
        "btn_add_trade": "➕ Добавить трейд",
        "btn_add_sale": "➕ Добавить продажу",
        "btn_online": "🌐 Онлайн трейдеры",
        "btn_cart": "🛒 Корзина",
        "btn_chat": "💬 Чат",
        "btn_contract": "📜 Заключить контракт",
        "btn_ad": "📣 Реклама",
        "btn_admin_service": "🛡 Услуги админа",
        "btn_suggest": "💡 Предложение",
        "btn_search": "🔍 Поиск",
        "btn_referral": "🎁 Реферал",
        "btn_change_lang": "🌐 Сменить язык",
        "sub_msg": "👋 Привет! Подпишитесь на все каналы, чтобы использовать бот!",
        "sub_confirm": "✅ Подтвердить подписку",
        "not_subbed": "❌ Вы ещё не подписались на все каналы!",
        "muted_msg": "🔇 Вы получили мут! Осталось {rem}.",
        "no_trades": "🔄 Пока нет активных трейдов.\n\n➕ Нажмите *Добавить трейд*!",
        "no_sales": "📊 Пока нет активных продаж.\n\n➕ Нажмите *Добавить продажу*!",
        "choose_game": "🎮 В какой игре ваш предмет?\n\nВыберите игру:",
        "trade_title_prompt": "📦 Напишите заголовок трейда:",
        "photo_prompt": "📸 Отправьте фото (по желанию):",
        "bio_prompt": "📝 Напишите био (что предлагаете, что хотите) или пропустите:",
        "sale_name_prompt": "📦 Что хотите продать? Напишите название:",
        "cancel": "❌ Отмена",
        "skip": "⏭ Пропустить",
        "cancelled": "Отменено.",
        "trade_added": "✅ Трейд опубликован! *#{sid}*",
        "sale_added": "✅ Продажа опубликована! *#{sid}*\n📦 {name}\n💰 {price:,} {currency}",
        "new_trade_channel": "🔄 *НОВЫЙ ТРЕЙД*\n━━━━━━━━━━━━━━━━━━━━\n\n1️⃣ *Пользователь:* @{uname}\n\n2️⃣ *Предмет:*\n{item_name}\n\n3️⃣ *Описание:*\n{bio}\n\n4️⃣ 🎮 *Игра:* {game}\n\n4️⃣ 🔄 *Трейд*\n\n━━━━━━━━━━━━━━━━━━━━\n💬 Связь: @{uname}",
        "new_sale_channel": "🏷 *НОВАЯ ПРОДАЖА*\n━━━━━━━━━━━━━━━━━━━━\n\n1️⃣ *Пользователь:* @{uname}\n\n2️⃣ *Предмет:*\n{item_name}\n\n3️⃣ *Описание:*\n{bio}\n\n4️⃣ 🎮 *Игра:* {game}\n\n5️⃣ 🏷 *Продаётся* — {price} {currency}\n\n━━━━━━━━━━━━━━━━━━━━\n💬 Связь: @{uname}",
        "contact_btn": "💬 Связаться",
        "prev": "⬅️ Пред.",
        "next": "➡️ След.",
        "add_cart": "🛒 В корзину",
        "trade_label": "🔄 ТРЕЙД",
        "sale_label": "🛍 ПРОДАЖА",
        "btn_roblox_script": "🎮 Roblox Скрипт",
        "roblox_script_msg": "🎮 *Roblox Скрипты*\n\nЧтобы получить последние рабочие скрипты, перейдите в наш канал ниже:",
        "btn_roblox_script_link": "📂 Канал со скриптами",
        "btn_scammers": "🚨 Мошенники",
        "scam_menu_msg": "🚨 *Раздел мошенников*\n\nЗдесь вы можете проверить информацию о пользователях, которые обманывали других.",
        "btn_scam_view": "👀 Посмотреть мошенников",
        "btn_scam_search": "🔍 Поиск",
        "scam_search_prompt": "🔍 Введите @username пользователя, которого хотите проверить:",
        "scam_write_username": "✍️ Напишите @username:",
        "no_scammers": "🚨 Список мошенников пока пуст.",
        "scam_not_found": "✅ Этот пользователь не найден в списке мошенников.",
        "scam_found_warn": "⚠️ *ВНИМАНИЕ!* Этот пользователь есть в списке мошенников!",
        "choose_trade_category": "🔄 Трейды какой игры вы хотите посмотреть?\n\nВыберите категорию:",
        "choose_sale_category": "📊 Продажи какой игры вы хотите посмотреть?\n\nВыберите категорию:",
        "back_to_categories": "🔙 Категории",
        "no_trades_in_cat": "🔄 В этой категории пока нет трейдов.",
        "no_sales_in_cat": "📊 В этой категории пока нет продаж.",
        "title_min_len": "❌ Заголовок должен быть не менее 5 символов, напишите снова:",
        "trade_updated": "✅ Трейд успешно обновлён!",
        "sale_updated": "✅ Продажа успешно обновлена!",
        "edit_name_prompt": "✏️ Напишите новое название:",
        "edit_photo_prompt": "📸 Отправьте новое фото (можно пропустить):",
        "edit_bio_prompt": "📝 Напишите новое описание:",
        "edit_price_prompt": "💰 Введите новую цену (только цифры):",
        "only_number": "❌ Введите только число:",
        "choose_currency": "💱 Выберите валюту:",
        "currency_som": "💵 Сум (UZS)",
        "currency_robux": "🪙 Robux",
        "price_prompt": "💰 Напишите цену (в {cur}):",
        "no_permission": "❌ У вас нет прав!",
    }
}

def T(lang: str, key: str, **kwargs) -> str:
    text = LANGS.get(lang, LANGS["uz"]).get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text

# ═══════════════════════════════════════════════════════
# MONGODB
# ═══════════════════════════════════════════════════════
mongo_client   = AsyncIOMotorClient(MONGO_URI)
mdb            = mongo_client["roblox_bot"]
users          = mdb["users"]
deposits       = mdb["deposits"]
orders         = mdb["orders"]
trades         = mdb["trades"]
sales          = mdb["sales"]
suggestions    = mdb["suggestions"]
ads            = mdb["ads"]
cooldowns      = mdb["cooldowns"]
online_traders = mdb["online_traders"]
mutes_db       = mdb["mutes"]
trade_cart     = mdb["trade_cart"]
sale_cart      = mdb["sale_cart"]
scammers       = mdb["scammers"]

async def init_indexes():
    await users.create_index("user_id", unique=True)
    await deposits.create_index("user_id")
    await orders.create_index("user_id")
    await trades.create_index([("user_id", 1), ("status", 1)])
    await sales.create_index([("user_id", 1), ("status", 1)])
    await suggestions.create_index("user_id")
    await ads.create_index("user_id")
    await cooldowns.create_index([("user_id", 1), ("action", 1)], unique=True)
    await online_traders.create_index("user_id", unique=True)
    await mutes_db.create_index("user_id", unique=True)
    await scammers.create_index("tgid_norm")

# ═══════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════
def now():
    return datetime.now().strftime("%d.%m.%Y %H:%M")

def short_id(oid):
    return str(oid)[-6:].upper()

def esc_md(text) -> str:
    if text is None:
        return ""
    text = str(text)
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text

async def get_user(uid):
    return await users.find_one({"user_id": uid})

async def get_user_lang(uid) -> str:
    u = await users.find_one({"user_id": uid}, {"lang": 1})
    return (u or {}).get("lang", "uz")

async def set_user_lang(uid, lang):
    await users.update_one({"user_id": uid}, {"$set": {"lang": lang}}, upsert=True)

async def upsert_user(uid, uname, lang="uz"):
    upd = {
        "$set": {"username": uname, "last_seen": now()},
        "$setOnInsert": {"user_id": uid, "balance": 0, "total_deposited": 0, "joined": now(), "lang": lang}
    }
    await users.update_one({"user_id": uid}, upd, upsert=True)

async def get_balance(uid):
    u = await users.find_one({"user_id": uid}, {"balance": 1})
    return u["balance"] if u else 0

async def add_balance(uid, amt):
    await users.update_one({"user_id": uid}, {"$inc": {"balance": amt, "total_deposited": amt}})

async def sub_balance(uid, amt):
    await users.update_one({"user_id": uid}, {"$inc": {"balance": -amt}})

async def users_count():
    return await users.count_documents({})

async def all_user_ids():
    return [u["user_id"] async for u in users.find({}, {"user_id": 1})]

async def check_cooldown(uid: int, action: str) -> bool:
    from datetime import datetime as dt
    now_ts = dt.now().timestamp()
    rec = await cooldowns.find_one({"user_id": uid, "action": action})
    if rec:
        last = rec.get("last_at", 0)
        if now_ts - last < 86400:
            return False
    await cooldowns.update_one(
        {"user_id": uid, "action": action},
        {"$set": {"last_at": now_ts}},
        upsert=True
    )
    return True

async def cooldown_remaining(uid: int, action: str) -> str:
    from datetime import datetime as dt
    rec = await cooldowns.find_one({"user_id": uid, "action": action})
    if not rec:
        return "0"
    elapsed = dt.now().timestamp() - rec.get("last_at", 0)
    remaining = max(0, 86400 - elapsed)
    h = int(remaining // 3600)
    m = int((remaining % 3600) // 60)
    return f"{h} soat {m} daqiqa"

# deposits
async def add_deposit(uid, uname, nick, amount, photo_id):
    r = await deposits.insert_one({
        "user_id": uid, "username": uname, "roblox_nick": nick,
        "amount": amount, "photo_id": photo_id, "status": "pending", "created_at": now()
    })
    return r.inserted_id

async def get_deposit(did):
    return await deposits.find_one({"_id": ObjectId(str(did))})

async def approve_deposit(did):
    dep = await deposits.find_one({"_id": ObjectId(str(did))})
    if dep:
        await deposits.update_one({"_id": ObjectId(str(did))}, {"$set": {"status": "approved"}})
        await users.update_one({"user_id": dep["user_id"]}, {"$inc": {"balance": dep["amount"], "total_deposited": dep["amount"]}})

async def reject_deposit(did):
    await deposits.update_one({"_id": ObjectId(str(did))}, {"$set": {"status": "rejected"}})

# orders
async def add_order(uid, uname, nick, robux, price, mood="", order_type="robux", label=""):
    r = await orders.insert_one({
        "user_id": uid, "username": uname, "roblox_nick": nick,
        "robux_amount": robux, "price_sum": price, "mood": mood,
        "order_type": order_type, "label": label,
        "status": "pending", "created_at": now()
    })
    return r.inserted_id

async def get_order(oid):
    return await orders.find_one({"_id": ObjectId(str(oid))})

async def approve_order(oid):
    await orders.update_one({"_id": ObjectId(str(oid))}, {"$set": {"status": "approved"}})

async def reject_order(oid):
    o = await orders.find_one({"_id": ObjectId(str(oid))})
    if o and o["status"] == "pending":
        await orders.update_one({"_id": ObjectId(str(oid))}, {"$set": {"status": "rejected"}})
        await users.update_one({"user_id": o["user_id"]}, {"$inc": {"balance": o["price_sum"]}})

async def pending_orders():
    return [o async for o in orders.find({"status": "pending"}).sort("_id", -1).limit(10)]

# trades — lang field qo'shildi
async def add_trade(uid, uname, nick, name, bio, photo_id, lang="uz", game=""):
    r = await trades.insert_one({
        "user_id": uid, "username": uname, "roblox_nick": nick,
        "name": name, "bio": bio, "photo_id": photo_id,
        "lang": lang, "game": game,
        "status": "active", "created_at": now()
    })
    return r.inserted_id

async def get_trade(tid):
    return await trades.find_one({"_id": ObjectId(str(tid))})

async def active_trades(lang=None, game=None):
    query = {"status": "active"}
    if lang:
        query["lang"] = lang
    if game:
        query["game"] = game
    return [t async for t in trades.find(query).sort("_id", -1)]

async def my_trades(uid):
    return [t async for t in trades.find({"user_id": uid, "status": "active"}).sort("_id", -1)]

async def edit_trade(tid, name, bio, photo_id=None):
    upd = {"$set": {"name": name, "bio": bio}}
    if photo_id is not None:
        upd["$set"]["photo_id"] = photo_id
    await trades.update_one({"_id": ObjectId(str(tid))}, upd)

async def delete_trade(tid):
    await trades.update_one({"_id": ObjectId(str(tid))}, {"$set": {"status": "deleted"}})

# sales — lang field qo'shildi
async def add_sale(uid, uname, nick, name, bio, photo_id, currency, price, lang="uz", game=""):
    r = await sales.insert_one({
        "user_id": uid, "username": uname, "roblox_nick": nick,
        "name": name, "bio": bio, "photo_id": photo_id, "currency": currency,
        "price": price, "lang": lang, "game": game,
        "status": "active", "created_at": now()
    })
    return r.inserted_id

async def get_sale(sid):
    return await sales.find_one({"_id": ObjectId(str(sid))})

async def active_sales(lang=None, game=None):
    query = {"status": "active"}
    if lang:
        query["lang"] = lang
    if game:
        query["game"] = game
    return [s async for s in sales.find(query).sort("_id", -1)]

async def my_sales(uid):
    return [s async for s in sales.find({"user_id": uid, "status": "active"}).sort("_id", -1)]

async def edit_sale(sid, name, price, photo_id=None):
    upd = {"$set": {"name": name, "price": price}}
    if photo_id is not None:
        upd["$set"]["photo_id"] = photo_id
    await sales.update_one({"_id": ObjectId(str(sid))}, upd)

async def delete_sale(sid):
    await sales.update_one({"_id": ObjectId(str(sid))}, {"$set": {"status": "deleted"}})

# ═══════════════════════════════════════════════════════
# ONLINE TRADERS DB HELPERS
# ═══════════════════════════════════════════════════════
async def get_online_trader(uid: int):
    return await online_traders.find_one({"user_id": uid})

async def upsert_online_trader(uid: int, uname: str, nick: str, bio: str, photo_id):
    await online_traders.update_one(
        {"user_id": uid},
        {"$set": {
            "username": uname,
            "roblox_nick": nick,
            "bio": bio,
            "photo_id": photo_id,
            "updated_at": now()
        }, "$setOnInsert": {
            "user_id": uid,
            "is_online": True,
            "created_at": now()
        }},
        upsert=True
    )

async def all_online_traders():
    return [t async for t in online_traders.find().sort("_id", -1)]

async def set_trader_status(uid: int, is_online: bool):
    await online_traders.update_one(
        {"user_id": uid},
        {"$set": {"is_online": is_online}}
    )

# ═══════════════════════════════════════════════════════
# MASHKALAR (SCAMMERS) DB HELPERS
# ═══════════════════════════════════════════════════════
async def add_scammer(nick: str, tgid: str, photo_id, added_by: int):
    norm = tgid.strip().lstrip("@").lower()
    r = await scammers.insert_one({
        "nick": nick.strip(),
        "tgid": tgid.strip(),
        "tgid_norm": norm,
        "photo_id": photo_id,
        "added_by": added_by,
        "created_at": now()
    })
    return r.inserted_id

async def get_scammer(sid):
    return await scammers.find_one({"_id": ObjectId(str(sid))})

async def all_scammers():
    return [s async for s in scammers.find({}).sort("_id", -1)]

async def find_scammers_by_username(query: str):
    norm = query.strip().lstrip("@").lower()
    if not norm:
        return []
    return [s async for s in scammers.find({"tgid_norm": norm})]

async def delete_scammer(sid):
    await scammers.delete_one({"_id": ObjectId(str(sid))})

# ═══════════════════════════════════════════════════════
# REFERRAL DB HELPERS
# ═══════════════════════════════════════════════════════
referrals_db = mdb["referrals"]
private_orders_db = mdb["private_orders"]

async def get_ref_count(uid: int) -> int:
    u = await users.find_one({"user_id": uid}, {"ref_count": 1})
    return (u or {}).get("ref_count", 0)

async def add_ref(inviter_uid: int):
    await users.update_one({"user_id": inviter_uid}, {"$inc": {"ref_count": 1}})

async def get_referrer(uid: int):
    r = await referrals_db.find_one({"user_id": uid})
    return (r or {}).get("referred_by")

async def set_referrer(uid: int, inviter_uid: int):
    await referrals_db.update_one({"user_id": uid}, {"$set": {"user_id": uid, "referred_by": inviter_uid}}, upsert=True)

# Top 20 reyting
async def get_top_referrals(limit=20):
    cursor = users.find({"ref_count": {"$gt": 0}}).sort("ref_count", -1).limit(limit)
    return [u async for u in cursor]

# Private server orders
async def add_private_order(uid, uname, game, roblox_nick, player_count, ref_cost):
    r = await private_orders_db.insert_one({
        "user_id": uid, "username": uname, "game": game,
        "roblox_nick": roblox_nick, "player_count": player_count,
        "ref_cost": ref_cost, "submitted_nicks": [],
        "status": "pending", "created_at": now()
    })
    return r.inserted_id

async def get_private_order(oid):
    return await private_orders_db.find_one({"_id": ObjectId(str(oid))})

async def update_private_order_nicks(oid, nicks: list):
    await private_orders_db.update_one({"_id": ObjectId(str(oid))}, {"$set": {"submitted_nicks": nicks}})

async def approve_private_order(oid):
    await private_orders_db.update_one({"_id": ObjectId(str(oid))}, {"$set": {"status": "approved"}})

async def reject_private_order(oid):
    o = await private_orders_db.find_one({"_id": ObjectId(str(oid))})
    if o and o["status"] == "pending":
        await private_orders_db.update_one({"_id": ObjectId(str(oid))}, {"$set": {"status": "rejected"}})
        # Referallarni qaytarish
        await users.update_one({"user_id": o["user_id"]}, {"$inc": {"ref_count": o["ref_cost"]}})
    return o

# ═══════════════════════════════════════════════════════
# SAVAT DB HELPERS
# ═══════════════════════════════════════════════════════
async def add_to_trade_cart(uid: int, trade_id: str):
    exists = await trade_cart.find_one({"user_id": uid, "trade_id": trade_id})
    if exists:
        return False
    await trade_cart.insert_one({"user_id": uid, "trade_id": trade_id, "added_at": now()})
    return True

async def add_to_sale_cart(uid: int, sale_id: str):
    exists = await sale_cart.find_one({"user_id": uid, "sale_id": sale_id})
    if exists:
        return False
    await sale_cart.insert_one({"user_id": uid, "sale_id": sale_id, "added_at": now()})
    return True

async def get_trade_cart(uid: int):
    items = [i async for i in trade_cart.find({"user_id": uid})]
    result = []
    for item in items:
        t = await get_trade(item["trade_id"])
        if t and t.get("status") == "active":
            result.append(t)
    return result

async def get_sale_cart(uid: int):
    items = [i async for i in sale_cart.find({"user_id": uid})]
    result = []
    for item in items:
        s = await get_sale(item["sale_id"])
        if s and s.get("status") == "active":
            result.append(s)
    return result

async def remove_from_trade_cart(uid: int, trade_id: str):
    await trade_cart.delete_one({"user_id": uid, "trade_id": trade_id})

async def remove_from_sale_cart(uid: int, sale_id: str):
    await sale_cart.delete_one({"user_id": uid, "sale_id": sale_id})

# ═══════════════════════════════════════════════════════
# NARXLAR
# ═══════════════════════════════════════════════════════
ROBUX_PRICES = [
    (40, 7000), (80, 14000), (120, 21000), (160, 28000), (200, 35000),
    (240, 42000), (280, 49000), (320, 55000), (360, 61000), (500, 66000),
    (1000, 130000), (2000, 255000), (5250, 600000),
]

ROBLOX_PLUS_OPTIONS = [
    ("plus",      "Roblox Plus",      65000),
    ("plus500",   "Roblox Plus 500",  120000),
    ("plus1000",  "Roblox Plus 1000", 170000),
]

FREE_TRIAL_PRICE = 15000

# Privat server narxlari (referal soni)
PRIVATE_GAMES = [
    ("steal_brainrot", "🧠 Steal a Brainrot", 5),
    ("blox_fruit",     "🍎 Blox Fruit",        6),
    ("mm2",            "🔪 MM2",               4),
    ("escape_tsunami", "🌊 Escape Tsunami",    3),
    ("mystery_die",    "🎲 Mystery Die",       3),
]
PRIVATE_GAME_LABELS = {k: (label, cost) for k, label, cost in PRIVATE_GAMES}

def price_for(robux):
    for r, p in ROBUX_PRICES:
        if r == robux:
            return p
    return None

def plus_price_for(key):
    for k, label, price in ROBLOX_PLUS_OPTIONS:
        if k == key:
            return (label, price)
    return None

DEPOSIT_OPTIONS = [5000, 10000, 15000, 20000, 30000, 50000, 100000]

# ═══════════════════════════════════════════════════════
# STATES
# ═══════════════════════════════════════════════════════
class LangSelect(StatesGroup):
    choosing = State()

class Dep(StatesGroup):
    custom_amount = State()
    check_photo   = State()

class TradeAdd(StatesGroup):
    game  = State()
    name  = State()
    photo = State()
    bio   = State()

class TradeEdit(StatesGroup):
    name  = State()
    photo = State()
    bio   = State()

class BuyFlow(StatesGroup):
    nick = State()
    mood = State()

class SaleAdd(StatesGroup):
    game     = State()
    name     = State()
    photo    = State()
    bio      = State()
    currency = State()
    price    = State()

class SaleEdit(StatesGroup):
    name  = State()
    photo = State()
    price = State()

class Broadcast(StatesGroup):
    photo = State()
    text  = State()

class AdminCmd(StatesGroup):
    add_balance = State()
    sub_balance = State()
    quick_add_balance = State()
    quick_sub_balance = State()

class ScammerAdd(StatesGroup):
    nick  = State()
    tgid  = State()
    photo = State()

class ScammerSearch(StatesGroup):
    query = State()

class ContactAdmin(StatesGroup):
    photo   = State()
    message = State()

class SuggestBot(StatesGroup):
    photo   = State()
    message = State()

class AdFlow(StatesGroup):
    photo = State()
    bio   = State()

class OnlineTraderAdd(StatesGroup):
    photo = State()
    nick  = State()
    bio   = State()

class OnlineTraderEdit(StatesGroup):
    nick  = State()
    bio   = State()

class MuteFlow(StatesGroup):
    user_id  = State()
    duration = State()
    unit     = State()

class SearchFlow(StatesGroup):
    by_id   = State()
    by_name = State()

class PrivateServerFlow(StatesGroup):
    choose_game    = State()
    roblox_nick    = State()
    player_count   = State()
    submit_nicks   = State()

class RobloxPlusBuy(StatesGroup):
    nick = State()
    mood = State()

# ═══════════════════════════════════════════════════════
# BOT + DP
# ═══════════════════════════════════════════════════════
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp  = Dispatcher(storage=MemoryStorage())

# ═══════════════════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════════════════
CHANNEL_LABELS = {
    "@bulldrop_n1":      "1️⃣ @bulldrop_n1",
    "@uzbekroblox":      "2️⃣ @uzbekroblox",
    "@trade_chanel_uz":  "3️⃣ @trade_chanel_uz",
}

def lang_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🇺🇿 O'zbek tili", callback_data="setlang_uz")
    b.button(text="🇺🇸 English",     callback_data="setlang_en")
    b.button(text="🇷🇺 Русский",     callback_data="setlang_ru")
    b.adjust(1)
    return b.as_markup()

def sub_kb(missing_channels=None, lang="uz"):
    if missing_channels is None:
        missing_channels = REQUIRED_CHANNELS
    b = InlineKeyboardBuilder()
    for ch in missing_channels:
        label = CHANNEL_LABELS.get(ch, f"📢 {ch}")
        b.button(text=label, url=f"https://t.me/{ch.lstrip('@')}")
    b.button(text=T(lang, "sub_confirm"), callback_data="check_sub")
    b.adjust(1)
    return b.as_markup()

def main_kb(lang="uz"):
    b = ReplyKeyboardBuilder()
    b.button(text=T(lang, "btn_buy"))
    b.button(text=T(lang, "btn_profile"))
    b.button(text=T(lang, "btn_deposit"))
    b.button(text=T(lang, "btn_trades"))
    b.button(text=T(lang, "btn_sales"))
    b.button(text=T(lang, "btn_add_trade"))
    b.button(text=T(lang, "btn_add_sale"))
    b.button(text=T(lang, "btn_online"))
    b.button(text=T(lang, "btn_cart"))
    b.button(text=T(lang, "btn_chat"))
    b.button(text=T(lang, "btn_contract"))
    b.button(text=T(lang, "btn_ad"))
    b.button(text=T(lang, "btn_admin_service"))
    b.button(text=T(lang, "btn_suggest"))
    b.button(text=T(lang, "btn_search"))
    b.button(text=T(lang, "btn_referral"))
    b.button(text=T(lang, "btn_roblox_script"))
    b.button(text=T(lang, "btn_scammers"))
    b.button(text=T(lang, "btn_change_lang"))
    b.adjust(2, 2, 2, 2, 2, 1, 2, 1, 1, 1, 2, 1)
    return b.as_markup(resize_keyboard=True)

def cancel_kb(lang="uz"):
    b = ReplyKeyboardBuilder()
    b.button(text=T(lang, "cancel"))
    return b.as_markup(resize_keyboard=True)

def skip_cancel_kb(lang="uz"):
    b = ReplyKeyboardBuilder()
    b.button(text=T(lang, "skip"))
    b.button(text=T(lang, "cancel"))
    b.adjust(2)
    return b.as_markup(resize_keyboard=True)

def game_kb(prefix="tgame"):
    b = InlineKeyboardBuilder()
    for key, label in GAME_CATEGORIES:
        b.button(text=label, callback_data=f"{prefix}_{key}")
    b.adjust(2)
    return b.as_markup()

async def trade_category_kb(lang="uz"):
    b = InlineKeyboardBuilder()
    for key, label in GAME_CATEGORIES:
        cnt = await trades.count_documents({"status": "active", "lang": lang, "game": key})
        b.button(text=f"{label} ({cnt})", callback_data=f"tcat_{key}")
    b.adjust(2)
    return b.as_markup()

async def sale_category_kb(lang="uz"):
    b = InlineKeyboardBuilder()
    for key, label in GAME_CATEGORIES:
        cnt = await sales.count_documents({"status": "active", "lang": lang, "game": key})
        b.button(text=f"{label} ({cnt})", callback_data=f"scat_{key}")
    b.adjust(2)
    return b.as_markup()

# ═══════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════
async def not_subscribed_channels(uid: int) -> list:
    missing = []
    for ch in REQUIRED_CHANNELS:
        try:
            m = await bot.get_chat_member(chat_id=ch, user_id=uid)
            if m.status in ["left", "kicked", "banned"]:
                missing.append(ch)
        except Exception as e:
            logging.error(f"Sub check xato ({ch}): {e}")
            missing.append(ch)
    return missing

async def is_sub(uid: int) -> bool:
    missing = await not_subscribed_channels(uid)
    return len(missing) == 0

async def check_access(msg: types.Message, state: FSMContext) -> bool:
    uid = msg.from_user.id
    lang = await get_user_lang(uid)
    if not is_admin(uid) and await is_muted(uid):
        rem = await mute_remaining(uid)
        await msg.answer(T(lang, "muted_msg", rem=rem))
        return False
    missing = await not_subscribed_channels(uid)
    if missing:
        await msg.answer(T(lang, "sub_msg"), reply_markup=sub_kb(missing, lang))
        return False
    return True

async def _send_or_edit(cb: types.CallbackQuery, photo_id, text, markup):
    try:
        if photo_id:
            if cb.message.photo:
                # Rasmli xabarda rasm file_id ni tekshirish kerak emas — caption + markup yangilanadi
                # Lekin rasm o'zgargan bo'lsa (boshqa e'lon) delete + resend kerak
                # Har doim delete + resend qilamiz rasm uchun (eng ishonchli usul)
                await cb.message.delete()
                await cb.message.answer_photo(photo_id, caption=text, reply_markup=markup)
            else:
                await cb.message.delete()
                await cb.message.answer_photo(photo_id, caption=text, reply_markup=markup)
        else:
            if cb.message.photo:
                await cb.message.delete()
                await cb.message.answer(text, reply_markup=markup)
            else:
                await cb.message.edit_text(text, reply_markup=markup)
    except Exception as e:
        logging.warning(f"edit xato: {e}")
        try:
            if photo_id:
                await cb.message.answer_photo(photo_id, caption=text, reply_markup=markup)
            else:
                await cb.message.answer(text, reply_markup=markup)
        except Exception:
            pass

async def notify_admins(text: str, photo_id=None, markup=None):
    for aid in ADMIN_IDS:
        try:
            if photo_id:
                await bot.send_photo(aid, photo_id, caption=text, reply_markup=markup)
            else:
                await bot.send_message(aid, text, reply_markup=markup)
        except Exception as e:
            logging.error(f"Admin {aid} ga xabar yuborishda xato: {e}")

# ═══════════════════════════════════════════════════════
# KANALGA E'LON YUBORISH
# ═══════════════════════════════════════════════════════
async def post_trade_to_channel(uname: str, item_name: str, bio: str, lang: str, game: str = "", photo_id=None):
    game_label = GAME_LABELS.get(game, game)
    caption = T(lang, "new_trade_channel",
                uname=esc_md(uname), item_name=esc_md(item_name),
                bio=esc_md(bio or "—"), game=esc_md(game_label))
    b = InlineKeyboardBuilder()
    b.button(text=T(lang, "contact_btn"), url=f"https://t.me/{uname}")
    try:
        if photo_id:
            await bot.send_photo(TRADE_CHANNEL, photo_id, caption=caption, reply_markup=b.as_markup())
        else:
            await bot.send_message(TRADE_CHANNEL, caption, reply_markup=b.as_markup())
    except Exception as e:
        logging.error(f"Kanalga trade yuborishda xato: {e}")

async def post_sale_to_channel(uname: str, item_name: str, bio: str, price, currency: str, lang: str, game: str = "", photo_id=None):
    game_label = GAME_LABELS.get(game, game)
    caption = T(lang, "new_sale_channel",
                uname=esc_md(uname), item_name=esc_md(item_name),
                bio=esc_md(bio or "—"), price=f"{int(price):,}", currency=esc_md(currency),
                game=esc_md(game_label))
    b = InlineKeyboardBuilder()
    b.button(text=T(lang, "contact_btn"), url=f"https://t.me/{uname}")
    try:
        if photo_id:
            await bot.send_photo(TRADE_CHANNEL, photo_id, caption=caption, reply_markup=b.as_markup())
        else:
            await bot.send_message(TRADE_CHANNEL, caption, reply_markup=b.as_markup())
    except Exception as e:
        logging.error(f"Kanalga sotuv yuborishda xato: {e}")

async def post_online_trader_to_channel(uname: str, nick: str, bio: str, photo_id=None):
    caption = (
        "🌐 *YANGI ONLINE TRADER*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"1️⃣ *Foydalanuvchi:* @{esc_md(uname)}\n\n"
        f"2️⃣ *Roblox nik:*\n{esc_md(nick)}\n\n"
        f"3️⃣ *Bio:*\n{esc_md(bio or '—')}\n\n"
        "4️⃣ 🔄 *Trade*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 Murojaat: @{esc_md(uname)}"
    )
    b = InlineKeyboardBuilder()
    b.button(text="💬 Trade qilish", url=f"https://t.me/{uname}")
    try:
        if photo_id:
            await bot.send_photo(TRADE_CHANNEL, photo_id, caption=caption, reply_markup=b.as_markup())
        else:
            await bot.send_message(TRADE_CHANNEL, caption, reply_markup=b.as_markup())
    except Exception as e:
        logging.error(f"Kanalga online trader yuborishda xato: {e}")

# ═══════════════════════════════════════════════════════
# /START + TIL TANLASH
# ═══════════════════════════════════════════════════════
@dp.message(Command("start"))
async def cmd_start(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    # Referal payload tekshirish
    parts = msg.text.split(maxsplit=1)
    payload = parts[1].strip() if len(parts) > 1 else ""
    ref_uid = None
    if payload.startswith("ref"):
        try:
            ref_uid = int(payload[3:])
            if ref_uid == uid:
                ref_uid = None
        except ValueError:
            ref_uid = None

    missing = await not_subscribed_channels(uid)
    u = await get_user(uid)
    lang = (u or {}).get("lang", None)

    # Agar obunaga tegishli muammo bo'lsa — avval til bor-yo'qligini tekshir
    if missing:
        await msg.answer(
            "👋 Salom! / Hello! / Привет!\n\nAvval kanallarimizga obuna bo'ling:\n"
            "Please subscribe to our channels:\nПодпишитесь на наши каналы:",
            reply_markup=sub_kb(missing, lang or "uz")
        )
        return

    # Til tanlanmagan bo'lsa — til so'ra
    if not lang:
        await msg.answer(
            "🌐 Tilni tanlang / Choose language / Выберите язык:",
            reply_markup=lang_kb()
        )
        await state.set_state(LangSelect.choosing)
        return

    # Yangi foydalanuvchi bo'lsa va referal bo'lsa
    if not u and ref_uid:
        already = await get_referrer(uid)
        if not already:
            inviter = await get_user(ref_uid)
            if inviter:
                await set_referrer(uid, ref_uid)
                await add_ref(ref_uid)
                inviter_lang = inviter.get("lang", "uz")
                try:
                    ref_total = await get_ref_count(ref_uid)
                    await bot.send_message(ref_uid,
                        f"🎉 *Yangi referal qo'shildi!*\n\n"
                        f"👤 Siz taklif qilgan odam botga kirdi.\n"
                        f"🎁 Jami refallaringiz: *{ref_total}* ta",
                        reply_markup=main_kb(inviter_lang))
                except Exception:
                    pass

    await upsert_user(uid, msg.from_user.username or "user", lang)
    await msg.answer(
        T(lang, "start_welcome", name=msg.from_user.first_name),
        reply_markup=main_kb(lang)
    )

@dp.callback_query(F.data.startswith("setlang_"))
async def cb_setlang(cb: types.CallbackQuery, state: FSMContext):
    lang = cb.data.split("_")[1]
    uid = cb.from_user.id
    await set_user_lang(uid, lang)
    await upsert_user(uid, cb.from_user.username or "user", lang)
    await state.clear()
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.message.answer(
        T(lang, "start_welcome", name=cb.from_user.first_name),
        reply_markup=main_kb(lang)
    )
    await cb.answer()

# Tilni o'zgartirish tugmasi — barcha tillarda ishlaydi
async def _is_change_lang_btn(msg: types.Message) -> bool:
    for l in LANGS.values():
        if msg.text == l["btn_change_lang"]:
            return True
    return False

@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_change_lang") for l in LANGS)))
async def cmd_change_lang(msg: types.Message, state: FSMContext):
    await msg.answer(
        "🌐 Tilni tanlang / Choose language / Выберите язык:",
        reply_markup=lang_kb()
    )

@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    lang = await get_user_lang(uid)
    missing = await not_subscribed_channels(uid)
    if missing:
        await cb.answer(T(lang, "not_subbed"), show_alert=True)
        try:
            await cb.message.edit_reply_markup(reply_markup=sub_kb(missing, lang))
        except Exception:
            pass
        return
    try:
        await cb.message.delete()
    except Exception:
        pass
    # Til tanlanmagan bo'lsa so'ra
    u = await get_user(uid)
    if not u or not u.get("lang"):
        await cb.message.answer(
            "🌐 Tilni tanlang / Choose language / Выберите язык:",
            reply_markup=lang_kb()
        )
        await cb.answer()
        return
    await upsert_user(uid, cb.from_user.username or "user", u["lang"])
    await cb.message.answer(T(lang, "start_welcome", name=cb.from_user.first_name), reply_markup=main_kb(lang))
    await cb.answer()

# ═══════════════════════════════════════════════════════
# PROFIL
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_profile") for l in LANGS)))
async def cmd_profile(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    u    = await get_user(uid)
    tr   = await my_trades(uid)
    sl   = await my_sales(uid)
    ref_count = await get_ref_count(uid)
    b    = InlineKeyboardBuilder()
    if tr:
        b.button(text=f"🔄 **Mening tradelarim** ({len(tr)})", callback_data="my_trades_0")
    if sl:
        b.button(text=f"🛍 **Mening sotuvlarim** ({len(sl)})", callback_data="my_sales_0")
    b.button(text=f"🎁 **Referallarim** ({ref_count})", callback_data="my_refs")
    b.adjust(1)
    await msg.answer(
        f"👤 **Profilingiz**\n\n"
        f"🆔 ID: `{uid}`\n"
        f"💰 Balans: **{u.get('balance', 0):,} so'm**\n"
        f"📈 Jami kiritilgan: **{u.get('total_deposited', 0):,} so'm**\n"
        f"📅 Ro'yxat: {u.get('joined', '-')}\n\n"
        f"🔄 Faol tradelarim: {len(tr)}\n"
        f"🛍 Faol sotuvlarim: {len(sl)}\n"
        f"🎁 Referallarim: **{ref_count}** ta",
        reply_markup=b.as_markup()
    )

@dp.callback_query(F.data.startswith("my_trades_"))
async def cb_my_trades(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    page = int(cb.data.split("_")[2])
    items = await my_trades(uid)
    if not items:
        await cb.answer("Faol trade e'lonlaringiz yo'q!", show_alert=True)
        return
    page = max(0, min(page, len(items) - 1))
    t    = items[page]
    caption = f"🔄 *{esc_md(t['name'])}* [{page+1}/{len(items)}]\n📝 {esc_md(t.get('bio',''))}\n📅 {t['created_at']}"
    b = InlineKeyboardBuilder()
    if page > 0:
        b.button(text="⬅️", callback_data=f"my_trades_{page-1}")
    if page < len(items) - 1:
        b.button(text="➡️", callback_data=f"my_trades_{page+1}")
    b.button(text="✏️ Tahrirlash", callback_data=f"etrade_{t['_id']}")
    b.button(text="🗑 O'chirish",  callback_data=f"dtrade_{t['_id']}")
    b.adjust(2, 2)
    await _send_or_edit(cb, t.get("photo_id"), caption, b.as_markup())
    await cb.answer()

@dp.callback_query(F.data.startswith("my_sales_"))
async def cb_my_sales(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    page = int(cb.data.split("_")[2])
    items = await my_sales(uid)
    if not items:
        await cb.answer("Faol sotuv e'lonlaringiz yo'q!", show_alert=True)
        return
    page = max(0, min(page, len(items) - 1))
    s    = items[page]
    caption = f"🛍 *{esc_md(s['name'])}* [{page+1}/{len(items)}]\n💰 {s['price']:,} {s['currency']}\n📅 {s['created_at']}"
    b = InlineKeyboardBuilder()
    if page > 0:
        b.button(text="⬅️", callback_data=f"my_sales_{page-1}")
    if page < len(items) - 1:
        b.button(text="➡️", callback_data=f"my_sales_{page+1}")
    b.button(text="✏️ Tahrirlash", callback_data=f"esale_{s['_id']}")
    b.button(text="🗑 O'chirish",  callback_data=f"dsale_{s['_id']}")
    b.adjust(2, 2)
    await _send_or_edit(cb, s.get("photo_id"), caption, b.as_markup())
    await cb.answer()

# ═══════════════════════════════════════════════════════
# HISOB TO'LDIRISH
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_deposit") for l in LANGS)))
async def cmd_deposit(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    b = InlineKeyboardBuilder()
    for amt in DEPOSIT_OPTIONS:
        b.button(text=f"{amt:,} so'm", callback_data=f"damt_{amt}")
    b.button(text="✏️ Boshqa miqdor", callback_data="damt_custom")
    b.adjust(2)
    await msg.answer("💰 *Hisob to'ldirish*\n\nQancha to'ldirmoqchisiz?", reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("damt_"))
async def cb_damt(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    lang = await get_user_lang(uid)
    missing = await not_subscribed_channels(uid)
    if missing:
        await cb.answer(T(lang, "not_subbed"), show_alert=True)
        return
    if cb.data == "damt_custom":
        await cb.message.answer("✏️ Miqdorni yozing (so'mda, min 1000):", reply_markup=cancel_kb(lang))
        await state.set_state(Dep.custom_amount)
        await cb.answer()
        return
    amount = int(cb.data.split("_")[1])
    await state.update_data(dep_amount=amount)
    await _show_card(cb.message, amount)
    await cb.answer()

@dp.message(Dep.custom_amount)
async def dep_custom(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    txt = msg.text.strip().replace(" ", "").replace(",", "")
    if not txt.isdigit() or int(txt) < 1000:
        await msg.answer("❌ Minimum 1000 so'm kiriting:")
        return
    amount = int(txt)
    await state.update_data(dep_amount=amount)
    await _show_card(msg, amount)

async def _show_card(target, amount: int):
    b = InlineKeyboardBuilder()
    b.button(text="✅ To'lov qildim", callback_data="dep_paid")
    b.button(text="❌ Bekor qilish",  callback_data="dep_cancel")
    b.adjust(1)
    card_display = CARD_NUMBER.replace("-", "").replace(" ", "")
    card_display = " ".join([card_display[i:i+4] for i in range(0, len(card_display), 4)])
    text = (
        f"💳 *To'lov ma'lumotlari*\n\n"
        f"💰 Miqdor: *{amount:,} so'm*\n\n"
        f"🏦 Karta raqami:\n`{card_display}`\n\n"
        f"👤 Karta egasi: *{CARD_OWNER}*\n\n"
        f"📌 Karta raqamiga bosib nusxa oling, to'lovni amalga oshiring va ✅ To'lov qildim tugmasini bosing."
    )
    await target.answer(text, reply_markup=b.as_markup())

@dp.callback_query(F.data == "dep_paid")
async def cb_dep_paid(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    lang = await get_user_lang(uid)
    d = await state.get_data()
    if not d.get("dep_amount"):
        await cb.answer("❌ Xatolik! Qaytadan boshlang.", show_alert=True)
        await state.clear()
        return
    await cb.message.answer("📸 To'lov chekining rasmini yuboring (screenshot):", reply_markup=cancel_kb(lang))
    await state.set_state(Dep.check_photo)
    await cb.answer()

@dp.callback_query(F.data == "dep_cancel")
async def cb_dep_cancel(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    lang = await get_user_lang(uid)
    await state.clear()
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.message.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
    await cb.answer()

@dp.message(Dep.check_photo, F.photo)
async def dep_check_photo(msg: types.Message, state: FSMContext):
    uid      = msg.from_user.id
    uname    = msg.from_user.username or "user"
    d        = await state.get_data()
    amount   = d.get("dep_amount", 0)
    photo_id = msg.photo[-1].file_id
    did      = await add_deposit(uid, uname, "", amount, photo_id)
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"dok_{did}")
    b.button(text="❌ Rad etish",  callback_data=f"dno_{did}")
    b.adjust(2)
    await notify_admins(
        f"💰 *To'lov #{short_id(did)}*\n\n"
        f"👤 @{esc_md(uname)} (`{uid}`)\n"
        f"💵 Miqdor: *{amount:,} so'm*\n🕐 {now()}",
        photo_id=photo_id,
        markup=b.as_markup()
    )
    await state.clear()
    lang = await get_user_lang(uid)
    await msg.answer(f"✅ Chek yuborildi! Admin tasdiqlashini kuting.\n📋 To'lov #{short_id(did)}", reply_markup=main_kb(lang))

@dp.message(Dep.check_photo)
async def dep_not_photo(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await msg.answer("❌ Rasm yuboring (chek screenshoti):")

@dp.callback_query(F.data.startswith("dok_"))
async def cb_dok(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    did = cb.data.split("_")[1]
    dep = await get_deposit(did)
    if not dep or dep["status"] != "pending":
        await cb.answer("Allaqachon ko'rilgan!", show_alert=True)
        return
    await approve_deposit(did)
    user_lang = await get_user_lang(dep["user_id"])
    try:
        await bot.send_message(dep["user_id"], f"✅ To'lovingiz tasdiqlandi!\n💰 *{dep['amount']:,} so'm* hisobingizga qo'shildi!", reply_markup=main_kb(user_lang))
    except Exception:
        pass
    try:
        await cb.message.edit_caption(cb.message.caption + f"\n\n✅ TASDIQLANDI ({now()})")
    except Exception:
        pass
    await cb.answer("✅ Tasdiqlandi!")

@dp.callback_query(F.data.startswith("dno_"))
async def cb_dno(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌", show_alert=True)
        return
    did = cb.data.split("_")[1]
    dep = await get_deposit(did)
    if not dep or dep["status"] != "pending":
        await cb.answer("Allaqachon ko'rilgan!", show_alert=True)
        return
    await reject_deposit(did)
    user_lang = await get_user_lang(dep["user_id"])
    try:
        await bot.send_message(dep["user_id"], f"❌ To'lovingiz rad etildi.\n📋 #{short_id(ObjectId(str(did)))}\n\nAdmin bilan bog'laning.", reply_markup=main_kb(user_lang))
    except Exception:
        pass
    try:
        await cb.message.edit_caption(cb.message.caption + f"\n\n❌ RAD ETILDI ({now()})")
    except Exception:
        pass
    await cb.answer("❌ Rad etildi!")

# ═══════════════════════════════════════════════════════
# ROBUX SOTIB OLISH
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_buy") for l in LANGS)))
async def cmd_buy(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid = msg.from_user.id
    lang = await get_user_lang(uid)
    bal = await get_balance(uid)
    b = InlineKeyboardBuilder()
    for r, p in ROBUX_PRICES:
        b.button(text=f"**{r}** Rbx — {p:,} so'm", callback_data=f"buy_{r}")
    b.adjust(3)
    # Roblox Plus tugmalari
    b.button(text="━━━━ 🌟 Roblox Plus ━━━━", callback_data="plus_noop")
    for key, label, price in ROBLOX_PLUS_OPTIONS:
        b.button(text=f"✨ {label} — {price:,} so'm", callback_data=f"buyplus_{key}")
    b.button(text="🆓 Free Trial — 15.000 so'm", callback_data="buy_freetrial")
    b.adjust(3, 3, 3, 3, 1, 1, 1, 1, 1)
    await msg.answer(
        f"🌟 **Assalomu alaykum!**\n"
        f"💰 Balansingiz: **{bal:,} so'm**\n\n"
        f"📊 **ROBUX NARXLARI (PAKETLAR):**\n\n"
        f"👇 Quyidagilardan birini tanlang:",
        reply_markup=b.as_markup()
    )

@dp.callback_query(lambda cb: bool(cb.data) and cb.data.startswith("buy_") and cb.data[len("buy_"):].isdigit())
async def cb_buy(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    lang = await get_user_lang(uid)
    missing = await not_subscribed_channels(uid)
    if missing:
        await cb.answer(T(lang, "not_subbed"), show_alert=True)
        return
    u = await get_user(uid)
    if not u:
        await cb.answer("❌ Avval /start yozing!", show_alert=True)
        return
    robux = int(cb.data.split("_")[1])
    price = price_for(robux)
    if price is None:
        await cb.answer("❌ Noto'g'ri miqdor!", show_alert=True)
        return
    bal = await get_balance(uid)
    if bal < price:
        await cb.answer(f"❌ Hisobingiz yetarli emas!\nKerak: {price:,} so'm\nBalans: {bal:,} so'm", show_alert=True)
        return
    await state.update_data(buy_robux=robux, buy_price=price)
    await cb.message.answer("🎮 Roblox nikingizni kiriting:", reply_markup=cancel_kb(lang))
    await state.set_state(BuyFlow.nick)
    await cb.answer()

@dp.message(BuyFlow.nick)
async def buy_nick(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    nick = msg.text.strip()
    if len(nick) < 3:
        await msg.answer("❌ Nik kamida 3 ta belgi bo'lsin, qaytadan kiriting:")
        return
    await state.update_data(buy_nick=nick)
    await msg.answer("roblox parolingiz?", reply_markup=cancel_kb(lang))
    await state.set_state(BuyFlow.mood)

@dp.message(BuyFlow.mood)
async def buy_mood(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    mood = msg.text.strip()
    await state.update_data(buy_mood=mood)
    d = await state.get_data()
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data="buy_confirm")
    b.button(text="✏️ Tahrirlash", callback_data="buy_redo")
    b.adjust(2)
    await msg.answer(
        f"📋 *Ma'lumotlarni tekshiring*\n\n"
        f"🎮 Nik: `{esc_md(d['buy_nick'])}`\n"
        f"🪙 Robux: *{d['buy_robux']}*\n"
        f"💵 Narx: *{d['buy_price']:,} so'm*\n"
        f"😊 Parolingiz: {esc_md(mood)}\n\n"
        f"Hammasi to'g'ri bo'lsa tasdiqlang:",
        reply_markup=b.as_markup()
    )

@dp.callback_query(F.data == "buy_redo")
async def cb_buy_redo(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    lang = await get_user_lang(uid)
    await cb.message.answer("🎮 Roblox nikingizni qayta kiriting:", reply_markup=cancel_kb(lang))
    await state.set_state(BuyFlow.nick)
    await cb.answer()

@dp.callback_query(F.data == "buy_confirm")
async def cb_buy_confirm(cb: types.CallbackQuery, state: FSMContext):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    d    = await state.get_data()
    robux = d.get("buy_robux")
    price = d.get("buy_price")
    nick  = d.get("buy_nick")
    mood  = d.get("buy_mood", "")
    if not robux or not price or not nick:
        await cb.answer("❌ Xatolik! Qaytadan boshlang.", show_alert=True)
        await state.clear()
        return
    bal = await get_balance(uid)
    if bal < price:
        await cb.answer(f"❌ Hisobingiz yetarli emas!\nKerak: {price:,} so'm\nBalans: {bal:,} so'm", show_alert=True)
        await state.clear()
        return
    await sub_balance(uid, price)
    oid = await add_order(uid, cb.from_user.username or "user", nick, robux, price, mood)
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"ook_{oid}")
    b.button(text="❌ Rad etish", callback_data=f"ono_{oid}")
    b.adjust(2)
    await notify_admins(
        f"🛒 *Robux buyurtma #{short_id(oid)}*\n\n"
        f"1️⃣ Nik: `{esc_md(nick)}`\n"
        f"2️⃣ Robux: *{robux}*\n"
        f"3️⃣ Narx: *{price:,} so'm*\n"
        f"4️⃣ Parol: {esc_md(mood)}\n\n"
        f"👤 @{esc_md(cb.from_user.username or '-')} (`{uid}`)\n🕐 {now()}",
        markup=b.as_markup()
    )
    await state.clear()
    await cb.message.answer(
        f"✅ *Buyurtmangiz qabul qilindi!*\n\n"
        f"🪙 Robux: *{robux}*\n"
        f"💵 To'langan: *{price:,} so'm*\n"
        f"🎮 Nik: `{esc_md(nick)}`\n"
        f"📋 Buyurtma #{short_id(oid)}\n\n"
        f"😴 Admin tasdiqlagunicha 2 step ochirib qoyib kutib turing.",
        reply_markup=main_kb(lang)
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("ook_"))
async def cb_ook(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    oid = cb.data.split("_")[1]
    o   = await get_order(oid)
    if not o or o["status"] != "pending":
        await cb.answer("Allaqachon ko'rilgan!", show_alert=True)
        return
    await approve_order(oid)
    user_lang = await get_user_lang(o["user_id"])
    try:
        await bot.send_message(o["user_id"], f"🎉 *Robuxingiz tushdi!*\n🪙 {o['robux_amount']} Robux\n🎮 Nik: `{o.get('roblox_nick','-')}`\n📋 Buyurtma #{short_id(ObjectId(str(oid)))}", reply_markup=main_kb(user_lang))
    except Exception:
        pass
    try:
        await cb.message.edit_text(cb.message.text + f"\n\n✅ TASDIQLANDI ({now()})")
    except Exception:
        pass
    await cb.answer("✅ Tasdiqlandi!")

@dp.callback_query(F.data.startswith("ono_"))
async def cb_ono(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    oid = cb.data.split("_")[1]
    o   = await get_order(oid)
    if not o or o["status"] != "pending":
        await cb.answer("Allaqachon ko'rilgan!", show_alert=True)
        return
    await reject_order(oid)
    user_lang = await get_user_lang(o["user_id"])
    try:
        await bot.send_message(o["user_id"], f"❌ Rad etildi.\n📋 Buyurtma #{short_id(ObjectId(str(oid)))}\n💰 {o['price_sum']:,} so'm hisobingizga qaytarildi.", reply_markup=main_kb(user_lang))
    except Exception:
        pass
    try:
        await cb.message.edit_text(cb.message.text + f"\n\n❌ RAD ETILDI + pul qaytarildi ({now()})")
    except Exception:
        pass
    await cb.answer("❌ Rad etildi!")

# ═══════════════════════════════════════════════════════
# TRADELAR
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_trades") for l in LANGS)))
async def cmd_trades(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    items = await active_trades(lang)
    if not items:
        await msg.answer(T(lang, "no_trades"))
        return
    await msg.answer(T(lang, "choose_trade_category"), reply_markup=await trade_category_kb(lang))

@dp.callback_query(F.data.startswith("tcat_") & (F.data != "tcat_back"))
async def cb_tcat(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    game = cb.data[len("tcat_"):]
    items = await active_trades(lang, game)
    if not items:
        await cb.answer(T(lang, "no_trades_in_cat"), show_alert=True)
        return
    await _send_trade_page(cb, items, 0, lang=lang, game=game)
    await cb.answer()

@dp.callback_query(F.data == "tcat_back")
async def cb_tcat_back(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.message.answer(T(lang, "choose_trade_category"), reply_markup=await trade_category_kb(lang))
    await cb.answer()

async def _send_trade_page(target, items, page, is_cb=True, lang="uz", game=""):
    t       = items[page]
    game_label = GAME_LABELS.get(t.get("game", ""), "")
    caption = (
        f"🔄 *{T(lang, 'trade_label')} #{short_id(t['_id'])}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"[{page+1}/{len(items)}]\n\n"
        f"👤 @{esc_md(t.get('username', '-'))}\n\n"
        f"📦 *{esc_md(t['name'])}*\n\n"
        f"📝 {esc_md(t.get('bio') or '—')}\n\n"
    )
    if game_label:
        caption += f"🎮 *{esc_md(game_label)}*\n\n"
    caption += f"📅 {t['created_at']}\n━━━━━━━━━━━━━━━━━━━━"
    b = InlineKeyboardBuilder()
    if page > 0:
        b.button(text=T(lang, "prev"), callback_data=f"tp_{game}_{page-1}")
    if page < len(items) - 1:
        b.button(text=T(lang, "next"), callback_data=f"tp_{game}_{page+1}")
    uname = t.get("username", "")
    if uname:
        b.button(text=T(lang, "contact_btn"), url=f"https://t.me/{uname}")
    b.button(text=T(lang, "add_cart"), callback_data=f"add_trade_cart_{t['_id']}")
    if game:
        b.button(text=T(lang, "back_to_categories"), callback_data="tcat_back")
    b.adjust(2, 1, 1, 1)
    if is_cb:
        await _send_or_edit(target, t.get("photo_id"), caption, b.as_markup())
    else:
        if t.get("photo_id"):
            await target.answer_photo(t["photo_id"], caption=caption, reply_markup=b.as_markup())
        else:
            await target.answer(caption, reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("tp_"))
async def cb_tp(cb: types.CallbackQuery):
    uid   = cb.from_user.id
    lang  = await get_user_lang(uid)
    rest  = cb.data[len("tp_"):]
    game, _, page_s = rest.rpartition("_")
    page  = int(page_s)
    items = await active_trades(lang, game or None)
    if not items:
        await cb.answer(T(lang, "no_trades"), show_alert=True)
        return
    page = max(0, min(page, len(items) - 1))
    await _send_trade_page(cb, items, page, lang=lang, game=game)
    await cb.answer()

# ── Trade qo'shish ─────────────────────────────────────
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_add_trade") for l in LANGS)))
async def cmd_trade_add(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    await msg.answer(T(lang, "choose_game"), reply_markup=game_kb("tgame"))
    await state.set_state(TradeAdd.game)

@dp.callback_query(F.data.startswith("tgame_"))
async def ta_game(cb: types.CallbackQuery, state: FSMContext):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    game = cb.data[len("tgame_"):]
    await state.update_data(t_game=game)
    await cb.message.answer(T(lang, "trade_title_prompt"), reply_markup=cancel_kb(lang))
    await state.set_state(TradeAdd.name)
    await cb.answer()

@dp.message(TradeAdd.name)
async def ta_name(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    if len(msg.text.strip()) < 5:
        await msg.answer(T(lang, "title_min_len"))
        return
    await state.update_data(t_name=msg.text.strip())
    await msg.answer(T(lang, "photo_prompt"), reply_markup=skip_cancel_kb(lang))
    await state.set_state(TradeAdd.photo)

@dp.message(TradeAdd.photo, F.photo)
async def ta_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    await state.update_data(t_photo=msg.photo[-1].file_id)
    await msg.answer(T(lang, "bio_prompt"), reply_markup=skip_cancel_kb(lang))
    await state.set_state(TradeAdd.bio)

@dp.message(TradeAdd.photo)
async def ta_no_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await state.update_data(t_photo=None)
    await msg.answer(T(lang, "bio_prompt"), reply_markup=skip_cancel_kb(lang))
    await state.set_state(TradeAdd.bio)

@dp.message(TradeAdd.bio)
async def ta_bio(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    bio = "" if msg.text == T(lang, "skip") else msg.text.strip()
    d        = await state.get_data()
    uname    = msg.from_user.username or "user"
    photo_id = d.get("t_photo")
    game     = d.get("t_game", "")
    tid = await add_trade(uid, uname, "", d["t_name"], bio, photo_id, lang=lang, game=game)
    await state.clear()
    cap = f"🔄 Yangi trade #{short_id(tid)}\n👤 @{esc_md(uname)}\n📦 {esc_md(d['t_name'])}\n📝 {esc_md(bio or '-')}\n🎮 {GAME_LABELS.get(game,'')}"
    await notify_admins(cap, photo_id=photo_id)
    await post_trade_to_channel(uname, d["t_name"], bio, lang, game, photo_id)
    await msg.answer(T(lang, "trade_added", sid=short_id(tid)), reply_markup=main_kb(lang))

# ── Trade tahrirlash ────────────────────────────────────
@dp.callback_query(F.data.startswith("etrade_"))
async def cb_etrade(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    lang = await get_user_lang(uid)
    tid = cb.data.split("_")[1]
    t   = await get_trade(tid)
    if not t or (t["user_id"] != uid and not is_admin(uid)):
        await cb.answer("Ruxsat yo'q!", show_alert=True)
        return
    await state.update_data(edit_trade_id=tid)
    await cb.message.answer(T(lang, "edit_name_prompt"), reply_markup=cancel_kb(lang))
    await state.set_state(TradeEdit.name)
    await cb.answer()

@dp.message(TradeEdit.name)
async def etrade_name(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await state.update_data(new_name=msg.text.strip())
    await msg.answer(T(lang, "edit_photo_prompt"), reply_markup=skip_cancel_kb(lang))
    await state.set_state(TradeEdit.photo)

@dp.message(TradeEdit.photo, F.photo)
async def etrade_photo(msg: types.Message, state: FSMContext):
    await state.update_data(new_photo=msg.photo[-1].file_id)
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    await msg.answer(T(lang, "edit_bio_prompt"), reply_markup=cancel_kb(lang))
    await state.set_state(TradeEdit.bio)

@dp.message(TradeEdit.photo)
async def etrade_no_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    if msg.text == T(lang, "skip"):
        # Rasm o'zgarmaydi — "SKIP" sentinel qo'yamiz
        await state.update_data(new_photo="SKIP")
    else:
        # Rasm olib tashlansin (matn yuborildi)
        await state.update_data(new_photo=None)
    await msg.answer(T(lang, "edit_bio_prompt"), reply_markup=cancel_kb(lang))
    await state.set_state(TradeEdit.bio)

@dp.message(TradeEdit.bio)
async def etrade_bio(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    d = await state.get_data()
    photo_raw = d.get("new_photo")
    # "SKIP" => rasm o'zgarmaydi (None uzatamiz, lekin edit_trade uni o'zgartirmaydi)
    if photo_raw == "SKIP":
        photo = "KEEP"  # DB da o'zgartirmaslik uchun
    else:
        photo = photo_raw  # None => o'chirish, file_id => yangilash
    tid = d["edit_trade_id"]
    # DB update
    upd = {"$set": {"name": d["new_name"], "bio": msg.text.strip()}}
    if photo != "KEEP":
        upd["$set"]["photo_id"] = photo
    from bson import ObjectId as ObjId
    await trades.update_one({"_id": ObjId(str(tid))}, upd)
    await state.clear()
    await msg.answer(T(lang, "trade_updated"), reply_markup=main_kb(lang))

@dp.callback_query(F.data.startswith("dtrade_"))
async def cb_dtrade(cb: types.CallbackQuery):
    uid = cb.from_user.id
    tid = cb.data.split("_")[1]
    t   = await get_trade(tid)
    if not t or (t["user_id"] != uid and not is_admin(uid)):
        await cb.answer("Ruxsat yo'q!", show_alert=True)
        return
    await delete_trade(tid)
    try:
        if cb.message.photo:
            await cb.message.edit_caption("🗑 E'lon o'chirildi.")
        else:
            await cb.message.edit_text("🗑 E'lon o'chirildi.")
    except Exception:
        pass
    await cb.answer("✅ O'chirildi!")

@dp.callback_query(F.data.startswith("add_trade_cart_"))
async def cb_add_trade_cart(cb: types.CallbackQuery):
    uid = cb.from_user.id
    tid = cb.data[len("add_trade_cart_"):]
    added = await add_to_trade_cart(uid, tid)
    if added:
        await cb.answer("✅ Trade savatga qo'shildi!", show_alert=True)
    else:
        await cb.answer("ℹ️ Bu trade allaqachon savatda!", show_alert=True)

# ═══════════════════════════════════════════════════════
# SOTUVLAR
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_sales") for l in LANGS)))
async def cmd_sales(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid   = msg.from_user.id
    lang  = await get_user_lang(uid)
    items = await active_sales(lang)
    if not items:
        await msg.answer(T(lang, "no_sales"))
        return
    await msg.answer(T(lang, "choose_sale_category"), reply_markup=await sale_category_kb(lang))

@dp.callback_query(F.data.startswith("scat_") & (F.data != "scat_back"))
async def cb_scat(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    game = cb.data[len("scat_"):]
    items = await active_sales(lang, game)
    if not items:
        await cb.answer(T(lang, "no_sales_in_cat"), show_alert=True)
        return
    await _send_sale_page(cb, items, 0, lang=lang, game=game)
    await cb.answer()

@dp.callback_query(F.data == "scat_back")
async def cb_scat_back(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.message.answer(T(lang, "choose_sale_category"), reply_markup=await sale_category_kb(lang))
    await cb.answer()

async def _send_sale_page(target, items, page, is_cb=True, lang="uz", game=""):
    s       = items[page]
    game_label = GAME_LABELS.get(s.get("game", ""), "")
    caption = (
        f"🛍 *{T(lang, 'sale_label')} #{short_id(s['_id'])}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"[{page+1}/{len(items)}]\n\n"
        f"👤 @{esc_md(s.get('username', '-'))}\n\n"
        f"📦 *{esc_md(s['name'])}*\n\n"
        f"📝 {esc_md(s.get('bio') or '—')}\n\n"
        f"💰 *{s['price']:,} {s['currency']}*\n\n"
    )
    if game_label:
        caption += f"🎮 *{esc_md(game_label)}*\n\n"
    caption += f"📅 {s['created_at']}\n━━━━━━━━━━━━━━━━━━━━"
    b = InlineKeyboardBuilder()
    if page > 0:
        b.button(text=T(lang, "prev"), callback_data=f"sp_{game}_{page-1}")
    if page < len(items) - 1:
        b.button(text=T(lang, "next"), callback_data=f"sp_{game}_{page+1}")
    uname = s.get("username", "")
    if uname:
        b.button(text=T(lang, "contact_btn"), url=f"https://t.me/{uname}")
    b.button(text=T(lang, "add_cart"), callback_data=f"add_sale_cart_{s['_id']}")
    if game:
        b.button(text=T(lang, "back_to_categories"), callback_data="scat_back")
    b.adjust(2, 1, 1, 1)
    if is_cb:
        await _send_or_edit(target, s.get("photo_id"), caption, b.as_markup())
    else:
        if s.get("photo_id"):
            await target.answer_photo(s["photo_id"], caption=caption, reply_markup=b.as_markup())
        else:
            await target.answer(caption, reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("sp_"))
async def cb_sp(cb: types.CallbackQuery):
    uid   = cb.from_user.id
    lang  = await get_user_lang(uid)
    rest  = cb.data[len("sp_"):]
    game, _, page_s = rest.rpartition("_")
    page  = int(page_s)
    items = await active_sales(lang, game or None)
    if not items:
        await cb.answer(T(lang, "no_sales"), show_alert=True)
        return
    page = max(0, min(page, len(items) - 1))
    await _send_sale_page(cb, items, page, lang=lang, game=game)
    await cb.answer()

@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_add_sale") for l in LANGS)))
async def cmd_sale_add(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    await msg.answer(T(lang, "choose_game"), reply_markup=game_kb("sgame"))
    await state.set_state(SaleAdd.game)

@dp.callback_query(F.data.startswith("sgame_"))
async def sa_game(cb: types.CallbackQuery, state: FSMContext):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    game = cb.data[len("sgame_"):]
    await state.update_data(s_game=game)
    await cb.message.answer(T(lang, "sale_name_prompt"), reply_markup=cancel_kb(lang))
    await state.set_state(SaleAdd.name)
    await cb.answer()

@dp.message(SaleAdd.name)
async def sa_name(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await state.update_data(s_name=msg.text.strip())
    await msg.answer(T(lang, "photo_prompt"), reply_markup=skip_cancel_kb(lang))
    await state.set_state(SaleAdd.photo)

@dp.message(SaleAdd.photo, F.photo)
async def sa_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    await state.update_data(s_photo=msg.photo[-1].file_id)
    await msg.answer(T(lang, "bio_prompt"), reply_markup=skip_cancel_kb(lang))
    await state.set_state(SaleAdd.bio)

@dp.message(SaleAdd.photo)
async def sa_no_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await state.update_data(s_photo=None)
    await msg.answer(T(lang, "bio_prompt"), reply_markup=skip_cancel_kb(lang))
    await state.set_state(SaleAdd.bio)

@dp.message(SaleAdd.bio)
async def sa_bio(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    bio = "" if msg.text == T(lang, "skip") else msg.text.strip()
    await state.update_data(s_bio=bio)
    b = InlineKeyboardBuilder()
    b.button(text=T(lang, "currency_som"), callback_data="sc_som")
    b.button(text=T(lang, "currency_robux"),      callback_data="sc_robux")
    b.adjust(2)
    await msg.answer(T(lang, "choose_currency"), reply_markup=b.as_markup())
    await state.set_state(SaleAdd.currency)

@dp.callback_query(F.data.startswith("sc_"))
async def cb_sc(cb: types.CallbackQuery, state: FSMContext):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    cur = "so'm" if cb.data == "sc_som" else "Robux"
    await state.update_data(s_currency=cur)
    await cb.message.answer(T(lang, "price_prompt", cur=cur), reply_markup=cancel_kb(lang))
    await state.set_state(SaleAdd.price)
    await cb.answer()

@dp.message(SaleAdd.price)
async def sa_price(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    txt = msg.text.strip().replace(" ", "").replace(",", "")
    if not txt.isdigit():
        await msg.answer(T(lang, "only_number"))
        return
    d     = await state.get_data()
    uname = msg.from_user.username or "user"
    bio   = d.get("s_bio", "")
    game  = d.get("s_game", "")
    sid   = await add_sale(uid, uname, "", d["s_name"], bio, d.get("s_photo"), d["s_currency"], int(txt), lang=lang, game=game)
    await state.clear()
    cap = f"🛍 Yangi sotuv #{short_id(sid)}\n👤 @{esc_md(uname)}\n📦 {esc_md(d['s_name'])}\n📝 {esc_md(bio or '-')}\n💰 {int(txt):,} {d['s_currency']}\n🎮 {GAME_LABELS.get(game,'')}"
    await notify_admins(cap, photo_id=d.get("s_photo"))
    await post_sale_to_channel(uname, d["s_name"], bio, int(txt), d["s_currency"], lang, game, d.get("s_photo"))
    await msg.answer(T(lang, "sale_added", sid=short_id(sid), name=d['s_name'], price=int(txt), currency=d['s_currency']), reply_markup=main_kb(lang))

@dp.callback_query(F.data.startswith("esale_"))
async def cb_esale(cb: types.CallbackQuery, state: FSMContext):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    sid = cb.data.split("_")[1]
    s   = await get_sale(sid)
    if not s or (s["user_id"] != uid and not is_admin(uid)):
        await cb.answer("Ruxsat yo'q!", show_alert=True)
        return
    await state.update_data(edit_sale_id=sid)
    await cb.message.answer(T(lang, "edit_name_prompt"), reply_markup=cancel_kb(lang))
    await state.set_state(SaleEdit.name)
    await cb.answer()

@dp.message(SaleEdit.name)
async def esale_name(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await state.update_data(new_name=msg.text.strip())
    await msg.answer(T(lang, "edit_photo_prompt"), reply_markup=skip_cancel_kb(lang))
    await state.set_state(SaleEdit.photo)

@dp.message(SaleEdit.photo, F.photo)
async def esale_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    await state.update_data(new_photo=msg.photo[-1].file_id)
    await msg.answer(T(lang, "edit_price_prompt"), reply_markup=cancel_kb(lang))
    await state.set_state(SaleEdit.price)

@dp.message(SaleEdit.photo)
async def esale_no_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    if msg.text == T(lang, "skip"):
        await state.update_data(new_photo="SKIP")
    else:
        await state.update_data(new_photo=None)
    await msg.answer(T(lang, "edit_price_prompt"), reply_markup=cancel_kb(lang))
    await state.set_state(SaleEdit.price)

@dp.message(SaleEdit.price)
async def esale_price(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    txt = msg.text.strip().replace(" ", "")
    if not txt.isdigit():
        await msg.answer(T(lang, "only_number"))
        return
    d = await state.get_data()
    photo_raw = d.get("new_photo")
    sid = d["edit_sale_id"]
    from bson import ObjectId as ObjId
    upd = {"$set": {"name": d["new_name"], "price": int(txt)}}
    if photo_raw != "SKIP":
        upd["$set"]["photo_id"] = photo_raw  # None = o'chirish, file_id = yangilash
    await sales.update_one({"_id": ObjId(str(sid))}, upd)
    await state.clear()
    await msg.answer(T(lang, "sale_updated"), reply_markup=main_kb(lang))

@dp.callback_query(F.data.startswith("dsale_"))
async def cb_dsale(cb: types.CallbackQuery):
    uid = cb.from_user.id
    sid = cb.data.split("_")[1]
    s   = await get_sale(sid)
    if not s or (s["user_id"] != uid and not is_admin(uid)):
        await cb.answer("Ruxsat yo'q!", show_alert=True)
        return
    await delete_sale(sid)
    try:
        if cb.message.photo:
            await cb.message.edit_caption("🗑 E'lon o'chirildi.")
        else:
            await cb.message.edit_text("🗑 E'lon o'chirildi.")
    except Exception:
        pass
    await cb.answer("✅ O'chirildi!")

@dp.callback_query(F.data.startswith("add_sale_cart_"))
async def cb_add_sale_cart(cb: types.CallbackQuery):
    uid = cb.from_user.id
    sid = cb.data[len("add_sale_cart_"):]
    added = await add_to_sale_cart(uid, sid)
    if added:
        await cb.answer("✅ Sotuv savatga qo'shildi!", show_alert=True)
    else:
        await cb.answer("ℹ️ Bu sotuv allaqachon savatda!", show_alert=True)

# ═══════════════════════════════════════════════════════
# 🛒 SAVAT
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_cart") for l in LANGS)))
async def cmd_cart(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Trade savati", callback_data="cart_trades")
    b.button(text="🛍 Sotuv savati", callback_data="cart_sales")
    b.adjust(2)
    await msg.answer("🛒 *Savat*\n\nQaysi savatni ko'rmoqchisiz?", reply_markup=b.as_markup())

@dp.callback_query(F.data == "cart_trades")
async def cb_cart_trades(cb: types.CallbackQuery):
    uid   = cb.from_user.id
    items = await get_trade_cart(uid)
    if not items:
        await cb.answer("🛒 Trade savatingiz bo'sh!", show_alert=True)
        return
    for t in items:
        b = InlineKeyboardBuilder()
        b.button(text="🗑 Olib tashlash", callback_data=f"remove_tcart_{t['_id']}")
        uname = t.get("username", "")
        if uname:
            b.button(text="💬 Murojaat", url=f"https://t.me/{uname}")
        b.adjust(2)
        cap = (
            f"🔄 *{esc_md(t['name'])}*\n"
            f"👤 @{esc_md(t.get('username','-'))}\n"
            f"📝 {esc_md(t.get('bio') or '—')}\n"
            f"📅 {t['created_at']}"
        )
        if t.get("photo_id"):
            await cb.message.answer_photo(t["photo_id"], caption=cap, reply_markup=b.as_markup())
        else:
            await cb.message.answer(cap, reply_markup=b.as_markup())
    await cb.answer()

@dp.callback_query(F.data == "cart_sales")
async def cb_cart_sales(cb: types.CallbackQuery):
    uid   = cb.from_user.id
    items = await get_sale_cart(uid)
    if not items:
        await cb.answer("🛒 Sotuv savatingiz bo'sh!", show_alert=True)
        return
    for s in items:
        b = InlineKeyboardBuilder()
        b.button(text="🗑 Olib tashlash", callback_data=f"remove_scart_{s['_id']}")
        uname = s.get("username", "")
        if uname:
            b.button(text="💬 Murojaat", url=f"https://t.me/{uname}")
        b.adjust(2)
        cap = (
            f"🛍 *{esc_md(s['name'])}*\n"
            f"👤 @{esc_md(s.get('username','-'))}\n"
            f"📝 {esc_md(s.get('bio') or '—')}\n"
            f"💰 {s['price']:,} {s['currency']}\n"
            f"📅 {s['created_at']}"
        )
        if s.get("photo_id"):
            await cb.message.answer_photo(s["photo_id"], caption=cap, reply_markup=b.as_markup())
        else:
            await cb.message.answer(cap, reply_markup=b.as_markup())
    await cb.answer()

@dp.callback_query(F.data.startswith("remove_tcart_"))
async def cb_remove_tcart(cb: types.CallbackQuery):
    uid = cb.from_user.id
    tid = cb.data[len("remove_tcart_"):]
    await remove_from_trade_cart(uid, tid)
    try:
        if cb.message.photo:
            await cb.message.edit_caption("🗑 Savatdan olib tashlandi.")
        else:
            await cb.message.edit_text("🗑 Savatdan olib tashlandi.")
    except Exception:
        pass
    await cb.answer("✅ Olib tashlandi!")

@dp.callback_query(F.data.startswith("remove_scart_"))
async def cb_remove_scart(cb: types.CallbackQuery):
    uid = cb.from_user.id
    sid = cb.data[len("remove_scart_"):]
    await remove_from_sale_cart(uid, sid)
    try:
        if cb.message.photo:
            await cb.message.edit_caption("🗑 Savatdan olib tashlandi.")
        else:
            await cb.message.edit_text("🗑 Savatdan olib tashlandi.")
    except Exception:
        pass
    await cb.answer("✅ Olib tashlandi!")

# ═══════════════════════════════════════════════════════
# 🌐 ONLINE TRADERLAR
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_online") for l in LANGS)))
async def cmd_online_traders(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    b = InlineKeyboardBuilder()
    b.button(text="➕ Trader qo'shish", callback_data="ot_add")
    b.button(text="👥 Online traderlarni ko'rish", callback_data="ot_list")
    b.button(text="🟢 Online / Offline", callback_data="ot_toggle")
    b.adjust(1)
    await msg.answer(
        "🌐 *Assalomu alaykum hurmatli foydalanuvchi!*\n\n"
        "Online trader qo'shish yoki ko'rish uchun quyidagi bo'limlarni bosing:",
        reply_markup=b.as_markup()
    )

@dp.callback_query(F.data == "ot_add")
async def cb_ot_add(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    lang = await get_user_lang(uid)
    existing = await get_online_trader(uid)
    if existing:
        b = InlineKeyboardBuilder()
        b.button(text="✏️ Ma'lumotlarni yangilash", callback_data="ot_edit")
        b.button(text="🔙 Orqaga", callback_data="ot_back")
        b.adjust(1)
        await cb.message.answer("ℹ️ Siz allaqachon online trader sifatida ro'yxatdasiz.", reply_markup=b.as_markup())
        await cb.answer()
        return
    await cb.message.answer("📸 Rasm yuboring (ixtiyoriy):", reply_markup=skip_cancel_kb(lang))
    await state.set_state(OnlineTraderAdd.photo)
    await cb.answer()

@dp.message(OnlineTraderAdd.photo, F.photo)
async def ot_add_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    await state.update_data(ot_photo=msg.photo[-1].file_id)
    await msg.answer("🎮 Robloxdagi nikinigiz nima?", reply_markup=cancel_kb(lang))
    await state.set_state(OnlineTraderAdd.nick)

@dp.message(OnlineTraderAdd.photo)
async def ot_add_no_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await state.update_data(ot_photo=None)
    await msg.answer("🎮 Robloxdagi nikinigiz nima?", reply_markup=cancel_kb(lang))
    await state.set_state(OnlineTraderAdd.nick)

@dp.message(OnlineTraderAdd.nick)
async def ot_add_nick(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await state.update_data(ot_nick=msg.text.strip())
    await msg.answer("📝 Bio yozing:", reply_markup=cancel_kb(lang))
    await state.set_state(OnlineTraderAdd.bio)

@dp.message(OnlineTraderAdd.bio)
async def ot_add_bio(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    d      = await state.get_data()
    uname  = msg.from_user.username or "user"
    await upsert_online_trader(uid, uname, d["ot_nick"], msg.text.strip(), d.get("ot_photo"))
    await post_online_trader_to_channel(uname, d["ot_nick"], msg.text.strip(), d.get("ot_photo"))
    await state.clear()
    await msg.answer("✅ *Siz Online Traderlar ro'yxatiga qo'shildingiz!*\n\n🟢 Holat: Online", reply_markup=main_kb(lang))

@dp.callback_query(F.data == "ot_list")
async def cb_ot_list(cb: types.CallbackQuery):
    items = await all_online_traders()
    if not items:
        await cb.answer("Hozircha online traderlar yo'q!", show_alert=True)
        return
    await cb.answer()
    await _send_ot_page(cb.message, items, 0, is_msg=True)

async def _send_ot_page(target, items: list, page: int, is_msg=False):
    t   = items[page]
    status = "🟢 Online" if t.get("is_online") else "🔴 Offline"
    caption = (
        f"🌐 *ONLINE TRADER #{page+1}/{len(items)}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 @{esc_md(t.get('username','-'))}\n"
        f"🎮 Roblox nik: `{esc_md(t.get('roblox_nick','-'))}`\n"
        f"📝 Bio: {esc_md(t.get('bio','—'))}\n"
        f"📊 Holat: {status}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    b = InlineKeyboardBuilder()
    if page > 0:
        b.button(text="⬅️ Oldingi", callback_data=f"otp_{page-1}")
    if page < len(items) - 1:
        b.button(text="➡️ Keyingi", callback_data=f"otp_{page+1}")
    uname = t.get("username", "")
    if uname:
        b.button(text="💬 Trade qilish", url=f"https://t.me/{uname}")
    b.adjust(2, 1)
    if is_msg:
        if t.get("photo_id"):
            await target.answer_photo(t["photo_id"], caption=caption, reply_markup=b.as_markup())
        else:
            await target.answer(caption, reply_markup=b.as_markup())
    else:
        await _send_or_edit(target, t.get("photo_id"), caption, b.as_markup())

@dp.callback_query(F.data.startswith("otp_"))
async def cb_otp(cb: types.CallbackQuery):
    page  = int(cb.data.split("_")[1])
    items = await all_online_traders()
    if not items:
        await cb.answer("Traderlar yo'q!", show_alert=True)
        return
    page = max(0, min(page, len(items) - 1))
    await _send_ot_page(cb, items, page, is_msg=False)
    await cb.answer()

@dp.callback_query(F.data == "ot_toggle")
async def cb_ot_toggle(cb: types.CallbackQuery):
    uid = cb.from_user.id
    doc = await get_online_trader(uid)
    if not doc:
        await cb.answer("❌ Avval ro'yxatdan o'ting! (Trader qo'shish)", show_alert=True)
        return
    new_status = not doc.get("is_online", True)
    await set_trader_status(uid, new_status)
    status_text = "🟢 Online" if new_status else "🔴 Offline"
    await cb.answer(f"✅ Holat o'zgartirildi: {status_text}", show_alert=True)

@dp.callback_query(F.data == "ot_edit")
async def cb_ot_edit(cb: types.CallbackQuery, state: FSMContext):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    await cb.message.answer("🎮 Yangi Roblox nikinigizni kiriting:", reply_markup=cancel_kb(lang))
    await state.set_state(OnlineTraderEdit.nick)
    await cb.answer()

@dp.message(OnlineTraderEdit.nick)
async def ot_edit_nick(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await state.update_data(ot_new_nick=msg.text.strip())
    await msg.answer("📝 Yangi bio yozing:", reply_markup=cancel_kb(lang))
    await state.set_state(OnlineTraderEdit.bio)

@dp.message(OnlineTraderEdit.bio)
async def ot_edit_bio(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    d     = await state.get_data()
    uname = msg.from_user.username or "user"
    doc   = await get_online_trader(uid)
    photo = doc.get("photo_id") if doc else None
    await upsert_online_trader(uid, uname, d["ot_new_nick"], msg.text.strip(), photo)
    await state.clear()
    await msg.answer("✅ Ma'lumotlaringiz yangilandi!", reply_markup=main_kb(lang))

@dp.callback_query(F.data == "ot_back")
async def cb_ot_back(cb: types.CallbackQuery):
    b = InlineKeyboardBuilder()
    b.button(text="➕ Trader qo'shish", callback_data="ot_add")
    b.button(text="👥 Online traderlarni ko'rish", callback_data="ot_list")
    b.button(text="🟢 Online / Offline", callback_data="ot_toggle")
    b.adjust(1)
    try:
        await cb.message.edit_text("🌐 *Online Traders*", reply_markup=b.as_markup())
    except Exception:
        await cb.message.answer("🌐 *Online Traders*", reply_markup=b.as_markup())
    await cb.answer()

# ═══════════════════════════════════════════════════════
# CHAT
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_chat") for l in LANGS)))
async def cmd_chat(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    b = InlineKeyboardBuilder()
    b.button(text="💬 Chatga kirish", url=CHAT_LINK)
    await msg.answer("💬 Rasmiy chatimizga xush kelibsiz!", reply_markup=b.as_markup())

# ═══════════════════════════════════════════════════════
# 🎮 ROBLOX SKRIPT
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_roblox_script") for l in LANGS)))
async def cmd_roblox_script(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    b = InlineKeyboardBuilder()
    b.button(text=T(lang, "btn_roblox_script_link"), url=ROBLOX_SCRIPT_CHANNEL)
    b.adjust(1)
    await msg.answer(T(lang, "roblox_script_msg"), reply_markup=b.as_markup())

# ═══════════════════════════════════════════════════════
# 🚨 MASHKALAR (SCAMMERS)
# ═══════════════════════════════════════════════════════
def scam_menu_kb(lang="uz"):
    b = InlineKeyboardBuilder()
    b.button(text=T(lang, "btn_scam_view"), callback_data="scam_list_0")
    b.button(text=T(lang, "btn_scam_search"), callback_data="scam_search_start")
    b.adjust(1)
    return b.as_markup()

async def _send_scammer_page(target, items, page, lang="uz", is_cb=True):
    s = items[page]
    caption = (
        f"🚨 *MASHKA #{page+1}/{len(items)}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 *Nik:* {esc_md(s.get('nick','-'))}\n"
        f"🆔 *ID/Username:* `{esc_md(s.get('tgid','-'))}`\n"
        f"📅 {s.get('created_at','-')}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    b = InlineKeyboardBuilder()
    if page > 0:
        b.button(text=T(lang, "prev"), callback_data=f"scam_list_{page-1}")
    if page < len(items) - 1:
        b.button(text=T(lang, "next"), callback_data=f"scam_list_{page+1}")
    if isinstance(target, types.CallbackQuery) and is_admin(target.from_user.id):
        b.button(text="🗑 O'chirish", callback_data=f"scam_del_{s['_id']}")
    b.adjust(2, 1)
    if is_cb:
        await _send_or_edit(target, s.get("photo_id"), caption, b.as_markup())
    else:
        if s.get("photo_id"):
            await target.answer_photo(s["photo_id"], caption=caption, reply_markup=b.as_markup())
        else:
            await target.answer(caption, reply_markup=b.as_markup())

async def _send_scammer_result(msg: types.Message, s: dict):
    caption = (
        f"⚠️ *MASHKA TOPILDI!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 *Nik:* {esc_md(s.get('nick','-'))}\n"
        f"🆔 *ID/Username:* `{esc_md(s.get('tgid','-'))}`\n"
        f"📅 {s.get('created_at','-')}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    if s.get("photo_id"):
        await msg.answer_photo(s["photo_id"], caption=caption)
    else:
        await msg.answer(caption)

@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_scammers") for l in LANGS)))
async def cmd_scammers(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    await msg.answer(T(lang, "scam_menu_msg"), reply_markup=scam_menu_kb(lang))

@dp.callback_query(F.data.startswith("scam_list_"))
async def cb_scam_list(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    page = int(cb.data[len("scam_list_"):])
    items = await all_scammers()
    if not items:
        await cb.answer(T(lang, "no_scammers"), show_alert=True)
        return
    page = max(0, min(page, len(items) - 1))
    await _send_scammer_page(cb, items, page, lang=lang)
    await cb.answer()

@dp.callback_query(F.data.startswith("scam_del_"))
async def cb_scam_del(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer(T(await get_user_lang(cb.from_user.id), "no_permission"), show_alert=True)
        return
    sid = cb.data[len("scam_del_"):]
    await delete_scammer(sid)
    try:
        if cb.message.photo:
            await cb.message.edit_caption("🗑 O'chirildi.")
        else:
            await cb.message.edit_text("🗑 O'chirildi.")
    except Exception:
        pass
    await cb.answer("✅ O'chirildi!")

@dp.callback_query(F.data == "scam_search_start")
async def cb_scam_search_start(cb: types.CallbackQuery, state: FSMContext):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    await cb.message.answer(T(lang, "scam_write_username"), reply_markup=cancel_kb(lang))
    await state.set_state(ScammerSearch.query)
    await cb.answer()

@dp.message(ScammerSearch.query)
async def scam_search_handler(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    query = msg.text.strip()
    await state.clear()
    results = await find_scammers_by_username(query)
    if not results:
        await msg.answer(T(lang, "scam_not_found"), reply_markup=main_kb(lang))
        return
    await msg.answer(T(lang, "scam_found_warn"))
    for s in results:
        await _send_scammer_result(msg, s)
    await msg.answer("✅", reply_markup=main_kb(lang))

# ── Admin: Mashka qo'shish ──────────────────────────────
@dp.callback_query(F.data == "adm_addscam")
async def adm_addscam(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await cb.message.answer("✏️ Mashka (firibgar) nikini yozing:", reply_markup=cancel_kb())
    await state.set_state(ScammerAdd.nick)
    await cb.answer()

@dp.message(ScammerAdd.nick)
async def scam_add_nick(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await state.update_data(scam_nick=msg.text.strip())
    await msg.answer("🆔 Foydalanuvchi ID yoki @username kiriting:", reply_markup=cancel_kb(lang))
    await state.set_state(ScammerAdd.tgid)

@dp.message(ScammerAdd.tgid)
async def scam_add_tgid(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await state.update_data(scam_tgid=msg.text.strip())
    await msg.answer(T(lang, "photo_prompt"), reply_markup=skip_cancel_kb(lang))
    await state.set_state(ScammerAdd.photo)

@dp.message(ScammerAdd.photo, F.photo)
async def scam_add_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    d    = await state.get_data()
    sid  = await add_scammer(d["scam_nick"], d["scam_tgid"], msg.photo[-1].file_id, uid)
    await state.clear()
    await msg.answer(f"✅ Mashka qo'shildi! #{short_id(sid)}", reply_markup=main_kb(lang))

@dp.message(ScammerAdd.photo)
async def scam_add_no_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    d    = await state.get_data()
    sid  = await add_scammer(d["scam_nick"], d["scam_tgid"], None, uid)
    await state.clear()
    await msg.answer(f"✅ Mashka qo'shildi! #{short_id(sid)}", reply_markup=main_kb(lang))

@dp.callback_query(F.data.startswith("adm_scamlist_"))
async def adm_scamlist(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    lang  = await get_user_lang(cb.from_user.id)
    page  = int(cb.data[len("adm_scamlist_"):])
    items = await all_scammers()
    if not items:
        await cb.answer(T(lang, "no_scammers"), show_alert=True)
        return
    page = max(0, min(page, len(items) - 1))
    await _send_scammer_page(cb, items, page, lang=lang)
    await cb.answer()

# ═══════════════════════════════════════════════════════
# SHARTNOMA QILISH
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_contract") for l in LANGS)))
async def cmd_contract(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    b = InlineKeyboardBuilder()
    b.button(text="✉️ Adminga xabar yuborish", callback_data="send_admin_msg")
    b.adjust(1)
    await msg.answer(
        "📜 *Shartnoma qilish*\n\n"
        "👤 Admin: @notalonet\n\n"
        "💬 Admin bilan shartnoma asosida ishlash uchun quyidagi tugmani bosing.\n"
        "⏰ 24 soatda 1 marta xabar yuborish mumkin.",
        reply_markup=b.as_markup()
    )

@dp.callback_query(F.data == "send_admin_msg")
async def cb_send_admin_msg(cb: types.CallbackQuery, state: FSMContext):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    ok = await check_cooldown(uid, "contract")
    if not ok:
        rem = await cooldown_remaining(uid, "contract")
        await cb.answer(f"⏰ 24 soatda 1 marta yozsa bo'ladi!\n{rem} kutib turing.", show_alert=True)
        return
    await cb.message.answer("📸 Rasm yuboring (ixtiyoriy):", reply_markup=skip_cancel_kb(lang))
    await state.set_state(ContactAdmin.photo)
    await cb.answer()

@dp.message(ContactAdmin.photo, F.photo)
async def contact_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    await state.update_data(ca_photo=msg.photo[-1].file_id)
    await msg.answer("✍️ Xabaringizni yozing:", reply_markup=cancel_kb(lang))
    await state.set_state(ContactAdmin.message)

@dp.message(ContactAdmin.photo)
async def contact_no_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await state.update_data(ca_photo=None)
    await msg.answer("✍️ Xabaringizni yozing:", reply_markup=cancel_kb(lang))
    await state.set_state(ContactAdmin.message)

@dp.message(ContactAdmin.message)
async def contact_admin_text(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    uname = msg.from_user.username or "-"
    fname = msg.from_user.full_name
    d     = await state.get_data()
    photo = d.get("ca_photo")
    text = (
        f"📜 *Yangi xabar (Shartnoma)*\n\n"
        f"👤 Ism: {esc_md(fname)}\n"
        f"🔗 Username: @{esc_md(uname)}\n"
        f"🆔 ID: `{uid}`\n\n"
        f"💬 Xabar:\n{esc_md(msg.text)}"
    )
    await notify_admins(text, photo_id=photo)
    await state.clear()
    await msg.answer("✅ Xabaringiz adminga yuborildi!", reply_markup=main_kb(lang))

# ═══════════════════════════════════════════════════════
# ADMINLIK XIZMATI
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_admin_service") for l in LANGS)))
async def cmd_admin_service(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    b = InlineKeyboardBuilder()
    b.button(text="📩 Adminga yozish", url="https://t.me/notalonet")
    b.adjust(1)
    await msg.answer("🛡 *Adminlik xizmati*\n\n👤 Admin: @notalonet", reply_markup=b.as_markup())

# ═══════════════════════════════════════════════════════
# TAKLIF BERISH
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_suggest") for l in LANGS)))
async def cmd_suggest(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    await msg.answer(
        "💡 *Bot uchun taklif berish*\n\n"
        "📸 Rasm tashlasangiz bo'ladi (ixtiyoriy).\n"
        "⏰ 24 soatda 1 marta taklif berish mumkin.",
        reply_markup=skip_cancel_kb(lang)
    )
    await state.set_state(SuggestBot.photo)

@dp.message(SuggestBot.photo, F.photo)
async def suggest_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    await state.update_data(sg_photo=msg.photo[-1].file_id)
    await msg.answer("✍️ Taklifingizni yozing:", reply_markup=cancel_kb(lang))
    await state.set_state(SuggestBot.message)

@dp.message(SuggestBot.photo)
async def suggest_no_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await state.update_data(sg_photo=None)
    await msg.answer("✍️ Taklifingizni yozing:", reply_markup=cancel_kb(lang))
    await state.set_state(SuggestBot.message)

@dp.message(SuggestBot.message)
async def suggest_message(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    uname = msg.from_user.username or "-"
    fname = msg.from_user.full_name
    ok = await check_cooldown(uid, "suggest")
    if not ok:
        rem = await cooldown_remaining(uid, "suggest")
        await state.clear()
        await msg.answer(f"⏰ 24 soatda 1 marta taklif bersa bo'ladi!\n{rem} kutib turing.", reply_markup=main_kb(lang))
        return
    d     = await state.get_data()
    photo = d.get("sg_photo")
    text = (
        f"💡 *Yangi taklif*\n\n"
        f"👤 Ism: {esc_md(fname)}\n"
        f"🔗 Username: @{esc_md(uname)}\n"
        f"🆔 ID: `{uid}`\n\n"
        f"💬 Taklif:\n{esc_md(msg.text)}"
    )
    await notify_admins(text, photo_id=photo)
    await state.clear()
    await msg.answer("✅ *Rahmat! Taklifingiz adminimizga yuborildi!* 🙏", reply_markup=main_kb(lang))

# ═══════════════════════════════════════════════════════
# REKLAMA QILISH
# ═══════════════════════════════════════════════════════
AD_PRICE = 5000

@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_ad") for l in LANGS)))
async def cmd_ad(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    bal = await get_balance(uid)
    b = InlineKeyboardBuilder()
    b.button(text="📣 Reklama berish", callback_data="ad_start")
    b.adjust(1)
    await msg.answer(
        f"📣 *Reklama qilish*\n\n"
        f"💰 Reklama narxi: *{AD_PRICE:,} so'm*\n"
        f"👛 Sizning balansingiz: *{bal:,} so'm*\n\n"
        f"Reklamangiz barcha bot foydalanuvchilariga yuboriladi!",
        reply_markup=b.as_markup()
    )

@dp.callback_query(F.data == "ad_start")
async def cb_ad_start(cb: types.CallbackQuery, state: FSMContext):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    bal = await get_balance(uid)
    if bal < AD_PRICE:
        await cb.answer(f"❌ Hisobingiz yetarli emas!\nKerak: {AD_PRICE:,} so'm\nBalans: {bal:,} so'm", show_alert=True)
        return
    await cb.message.answer("📸 Reklama uchun rasm yuboring:", reply_markup=cancel_kb(lang))
    await state.set_state(AdFlow.photo)
    await cb.answer()

@dp.message(AdFlow.photo, F.photo)
async def ad_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    await state.update_data(ad_photo=msg.photo[-1].file_id)
    await msg.answer("📝 Reklama matnini yozing:", reply_markup=cancel_kb(lang))
    await state.set_state(AdFlow.bio)

@dp.message(AdFlow.photo)
async def ad_no_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await msg.answer("❌ Iltimos rasm yuboring:")

@dp.message(AdFlow.bio)
async def ad_bio(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    uname = msg.from_user.username or "user"
    d     = await state.get_data()
    photo = d.get("ad_photo")
    bio   = msg.text.strip()
    bal = await get_balance(uid)
    if bal < AD_PRICE:
        await state.clear()
        await msg.answer("❌ Hisobingiz yetarli emas!", reply_markup=main_kb(lang))
        return
    await sub_balance(uid, AD_PRICE)
    await state.clear()
    uids = await all_user_ids()
    sent = 0
    ad_caption = f"📣 *REKLAMA*\n\n{esc_md(bio)}"
    for u_id in uids:
        try:
            await bot.send_photo(u_id, photo, caption=ad_caption)
            sent += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    await notify_admins(
        f"📣 *Yangi reklama*\n\n"
        f"👤 @{esc_md(uname)} (`{uid}`)\n"
        f"💰 To'langan: {AD_PRICE:,} so'm\n"
        f"📤 Yuborildi: {sent}/{len(uids)} ta"
    )
    await msg.answer(f"✅ Reklamangiz *{sent}* ta foydalanuvchiga yuborildi!\n💰 {AD_PRICE:,} so'm yechildi.", reply_markup=main_kb(lang))

# ═══════════════════════════════════════════════════════
# 🔍 QIDIRUV
# ═══════════════════════════════════════════════════════
def search_menu_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🆔 ID orqali qidirish",  callback_data="search_by_id")
    b.button(text="📝 Ism orqali qidirish", callback_data="search_by_name")
    b.adjust(1)
    return b.as_markup()

def _result_kb(kind: str, oid, username: str = ""):
    b = InlineKeyboardBuilder()
    if username:
        b.button(text="💬 Murojaat", url=f"https://t.me/{username}")
    if kind == "trade":
        b.button(text="🛒 Savatga solish", callback_data=f"add_trade_cart_{oid}")
    elif kind == "sale":
        b.button(text="🛒 Savatga solish", callback_data=f"add_sale_cart_{oid}")
    b.adjust(1)
    return b.as_markup()

async def _send_trade_result(msg: types.Message, t: dict):
    caption = (
        f"🔄 *Trade #{short_id(t['_id'])}*\n"
        f"👤 @{esc_md(t.get('username','-'))}\n"
        f"📦 {esc_md(t['name'])}\n"
        f"📝 {esc_md(t.get('bio') or '-')}\n"
        f"🎮 {GAME_LABELS.get(t.get('game',''),'')}\n"
        f"📅 {t.get('created_at','-')}"
    )
    kb = _result_kb("trade", t["_id"], t.get("username", ""))
    if t.get("photo_id"):
        await msg.answer_photo(t["photo_id"], caption=caption, reply_markup=kb)
    else:
        await msg.answer(caption, reply_markup=kb)

async def _send_sale_result(msg: types.Message, s: dict):
    caption = (
        f"🛍 *Sotuv #{short_id(s['_id'])}*\n"
        f"👤 @{esc_md(s.get('username','-'))}\n"
        f"📦 {esc_md(s['name'])}\n"
        f"📝 {esc_md(s.get('bio') or '-')}\n"
        f"💰 {s['price']:,} {esc_md(s['currency'])}\n"
        f"🎮 {GAME_LABELS.get(s.get('game',''),'')}\n"
        f"📅 {s.get('created_at','-')}"
    )
    kb = _result_kb("sale", s["_id"], s.get("username", ""))
    if s.get("photo_id"):
        await msg.answer_photo(s["photo_id"], caption=caption, reply_markup=kb)
    else:
        await msg.answer(caption, reply_markup=kb)

async def _send_ot_result(msg: types.Message, t: dict):
    status = "🟢 Online" if t.get("is_online") else "🔴 Offline"
    caption = (
        f"🌐 *Online Trader*\n"
        f"👤 @{esc_md(t.get('username','-'))}\n"
        f"🎮 Roblox nik: `{esc_md(t.get('roblox_nick','-'))}`\n"
        f"📝 {esc_md(t.get('bio') or '-')}\n"
        f"📊 Holat: {status}"
    )
    kb = _result_kb("ot", t.get("user_id"), t.get("username", ""))
    if t.get("photo_id"):
        await msg.answer_photo(t["photo_id"], caption=caption, reply_markup=kb)
    else:
        await msg.answer(caption, reply_markup=kb)

@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_search") for l in LANGS)))
async def cmd_search(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    await state.clear()
    await msg.answer("🔍 *Qidiruv bo'limi*\n\nQaysi usul bilan qidirmoqchisiz?", reply_markup=search_menu_kb())

@dp.callback_query(F.data == "search_by_id")
async def cb_search_by_id(cb: types.CallbackQuery, state: FSMContext):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    await cb.message.answer("🆔 ID yuboring (Telegram ID yoki e'lon ID):", reply_markup=cancel_kb(lang))
    await state.set_state(SearchFlow.by_id)
    await cb.answer()

@dp.callback_query(F.data == "search_by_name")
async def cb_search_by_name(cb: types.CallbackQuery, state: FSMContext):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    await cb.message.answer("📝 Roblox nik, e'lon nomi yoki @username yozing:", reply_markup=cancel_kb(lang))
    await state.set_state(SearchFlow.by_name)
    await cb.answer()

@dp.message(SearchFlow.by_id)
async def search_by_id_handler(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    query = msg.text.strip().lstrip("@")
    await state.clear()
    found = False
    if query.isdigit():
        uid_q = int(query)
        u = await get_user(uid_q)
        if u:
            found = True
            tr_count = len(await my_trades(uid_q))
            sl_count = len(await my_sales(uid_q))
            ot       = await get_online_trader(uid_q)
            ot_status = "🟢 Online" if (ot and ot.get("is_online")) else ("🔴 Offline" if ot else "—")
            await msg.answer(
                f"👤 *Foydalanuvchi topildi*\n"
                f"🆔 ID: `{uid_q}`\n"
                f"📛 Username: @{esc_md(u.get('username','-'))}\n"
                f"🔄 Faol tradelari: *{tr_count}*\n"
                f"🛍 Faol sotuvlari: *{sl_count}*\n"
                f"🌐 Online trader holati: {ot_status}"
            )
            for t in await my_trades(uid_q):
                await _send_trade_result(msg, t)
            for s in await my_sales(uid_q):
                await _send_sale_result(msg, s)
            if ot:
                await _send_ot_result(msg, ot)
    qid = query.upper()
    async for t in trades.find({"status": "active"}):
        if short_id(t["_id"]) == qid:
            found = True
            await _send_trade_result(msg, t)
    async for s in sales.find({"status": "active"}):
        if short_id(s["_id"]) == qid:
            found = True
            await _send_sale_result(msg, s)
    if not found:
        await msg.answer("❌ Hech narsa topilmadi.", reply_markup=main_kb(lang))
        return
    await msg.answer("✅ Qidiruv yakunlandi.", reply_markup=main_kb(lang))

@dp.message(SearchFlow.by_name)
async def search_by_name_handler(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    query = msg.text.strip().lstrip("@")
    await state.clear()
    if len(query) < 2:
        await msg.answer("❌ Kamida 2 ta belgi kiriting:", reply_markup=main_kb(lang))
        return
    import re as _re
    pattern = _re.compile(_re.escape(query), _re.IGNORECASE)
    found = False
    async for t in trades.find({"status": "active", "name": {"$regex": pattern}}).limit(10):
        found = True
        await _send_trade_result(msg, t)
    async for s in sales.find({"status": "active", "name": {"$regex": pattern}}).limit(10):
        found = True
        await _send_sale_result(msg, s)
    async for t in online_traders.find({"$or": [{"roblox_nick": {"$regex": pattern}}, {"username": {"$regex": pattern}}]}).limit(10):
        found = True
        await _send_ot_result(msg, t)
    if not found:
        await msg.answer("❌ Hech narsa topilmadi.", reply_markup=main_kb(lang))
        return
    await msg.answer("✅ Qidiruv yakunlandi.", reply_markup=main_kb(lang))

# ═══════════════════════════════════════════════════════
# MUTE TIZIMI
# ═══════════════════════════════════════════════════════
async def mute_user(uid: int, until_ts: float, reason: str = ""):
    await mutes_db.update_one(
        {"user_id": uid},
        {"$set": {"user_id": uid, "until": until_ts, "reason": reason, "muted_at": now()}},
        upsert=True
    )

async def unmute_user(uid: int):
    await mutes_db.delete_one({"user_id": uid})

async def is_muted(uid: int) -> bool:
    from datetime import datetime as dt
    rec = await mutes_db.find_one({"user_id": uid})
    if not rec:
        return False
    if rec["until"] < dt.now().timestamp():
        await mutes_db.delete_one({"user_id": uid})
        return False
    return True

async def mute_remaining(uid: int) -> str:
    from datetime import datetime as dt
    rec = await mutes_db.find_one({"user_id": uid})
    if not rec:
        return "0"
    remaining = max(0, rec["until"] - dt.now().timestamp())
    h = int(remaining // 3600)
    m = int((remaining % 3600) // 60)
    s = int(remaining % 60)
    if h > 0:
        return f"{h} soat {m} daqiqa"
    elif m > 0:
        return f"{m} daqiqa {s} soniya"
    return f"{s} soniya"

# ═══════════════════════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════════════════════
async def admin_panel_kb():
    tr  = await active_trades()
    sl  = await active_sales()
    or_ = await pending_orders()
    cnt = await users_count()
    scam_cnt = len(await all_scammers())
    b   = InlineKeyboardBuilder()
    b.button(text=f"📦 Buyurtmalar ({len(or_)})", callback_data="adm_ord")
    b.button(text=f"🔄 Tradelar ({len(tr)})",     callback_data="adm_tr")
    b.button(text=f"🛍 Sotuvlar ({len(sl)})",      callback_data="adm_sl")
    b.button(text="📢 Broadcast",                  callback_data="adm_bc")
    b.button(text="➕ Balans qo'shish",            callback_data="adm_addbal")
    b.button(text="➖ Balans ayirish",             callback_data="adm_subbal")
    b.button(text="🔇 Mute berish",                callback_data="adm_mute")
    b.button(text="👥 Foydalanuvchilar",           callback_data="adm_users_0")
    b.button(text=f"🚨 Mashka qo'shish",           callback_data="adm_addscam")
    b.button(text=f"🚨 Mashkalar ({scam_cnt})",    callback_data="adm_scamlist_0")
    b.adjust(2, 2, 2, 1, 2)
    return b.as_markup(), cnt, or_, tr, sl

@dp.message(Command("admin"))
async def cmd_admin(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("❌ Ruxsat yo'q!")
        return
    markup, cnt, or_, tr, sl = await admin_panel_kb()
    await msg.answer(
        f"🛠 *Admin Panel*\n\n👥 Foydalanuvchilar: *{cnt}*\n"
        f"📦 Kutayotgan buyurtmalar: *{len(or_)}*\n"
        f"🔄 Faol tradelar: *{len(tr)}*\n🛍 Faol sotuvlar: *{len(sl)}*",
        reply_markup=markup
    )

@dp.callback_query(F.data == "adm_ord")
async def adm_ord(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    ol = await pending_orders()
    if not ol:
        await cb.answer("Kutayotgan buyurtmalar yo'q!", show_alert=True)
        return
    for o in ol:
        b = InlineKeyboardBuilder()
        b.button(text="✅ Tasdiqlash", callback_data=f"ook_{o['_id']}")
        b.button(text="❌ Rad etish", callback_data=f"ono_{o['_id']}")
        b.adjust(2)
        await cb.message.answer(
            f"🛒 *Buyurtma #{short_id(o['_id'])}*\n👤 @{esc_md(o['username'])}\n"
            f"🎮 Nik: `{o.get('roblox_nick','-')}`\n"
            f"🪙 {o['robux_amount']} Robux — {o['price_sum']:,} so'm\n"
            f"😊 Qalaysiz: {o.get('mood','-')}\n🕐 {o['created_at']}",
            reply_markup=b.as_markup()
        )
    await cb.answer()

@dp.callback_query(F.data == "adm_tr")
async def adm_tr(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    items = await active_trades()
    if not items:
        await cb.answer("Tradelar yo'q!", show_alert=True)
        return
    for t in items[:10]:
        b = InlineKeyboardBuilder()
        b.button(text="✏️ Tahrirlash", callback_data=f"etrade_{t['_id']}")
        b.button(text="🗑 O'chirish",  callback_data=f"dtrade_{t['_id']}")
        b.adjust(2)
        caption = f"🔄 *#{short_id(t['_id'])}* {esc_md(t['name'])}\n👤 @{esc_md(t.get('username','-'))}\n📝 {esc_md(t['bio'])}\n🎮 {GAME_LABELS.get(t.get('game',''),'')}"
        if t.get("photo_id"):
            await cb.message.answer_photo(t["photo_id"], caption=caption, reply_markup=b.as_markup())
        else:
            await cb.message.answer(caption, reply_markup=b.as_markup())
    await cb.answer()

@dp.callback_query(F.data == "adm_sl")
async def adm_sl(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    items = await active_sales()
    if not items:
        await cb.answer("Sotuvlar yo'q!", show_alert=True)
        return
    for s in items[:10]:
        b = InlineKeyboardBuilder()
        b.button(text="✏️ Tahrirlash", callback_data=f"esale_{s['_id']}")
        b.button(text="🗑 O'chirish",  callback_data=f"dsale_{s['_id']}")
        b.adjust(2)
        caption = f"🛍 *#{short_id(s['_id'])}* {esc_md(s['name'])}\n👤 @{esc_md(s.get('username','-'))}\n📝 {esc_md(s.get('bio') or '-')}\n💰 {s['price']:,} {s['currency']}\n🎮 {GAME_LABELS.get(s.get('game',''),'')}"
        if s.get("photo_id"):
            await cb.message.answer_photo(s["photo_id"], caption=caption, reply_markup=b.as_markup())
        else:
            await cb.message.answer(caption, reply_markup=b.as_markup())
    await cb.answer()

@dp.callback_query(F.data == "adm_addbal")
async def adm_addbal(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await cb.message.answer("➕ Format: `<user_id> <summa>`\nMasalan: `123456789 50000`", reply_markup=cancel_kb())
    await state.set_state(AdminCmd.add_balance)
    await cb.answer()

@dp.message(AdminCmd.add_balance)
async def admin_addbalance(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel") or msg.text in ("❌ Bekor qilish", "❌ Cancel", "❌ Отмена"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    parts = msg.text.strip().split()
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await msg.answer("❌ Format: `<user_id> <summa>`")
        return
    uid_t, amt = int(parts[0]), int(parts[1])
    await users.update_one({"user_id": uid_t}, {"$inc": {"balance": amt}})
    user_lang = await get_user_lang(uid_t)
    try:
        await bot.send_message(uid_t, f"💰 Hisobingizga *{amt:,} so'm* qo'shildi!", reply_markup=main_kb(user_lang))
    except Exception:
        pass
    await state.clear()
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    await msg.answer(f"✅ {uid_t} ga {amt:,} so'm qo'shildi.", reply_markup=main_kb(lang))

@dp.callback_query(F.data == "adm_subbal")
async def adm_subbal(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await cb.message.answer("➖ Format: `<user_id> <summa>`\nMasalan: `123456789 50000`", reply_markup=cancel_kb())
    await state.set_state(AdminCmd.sub_balance)
    await cb.answer()

@dp.message(AdminCmd.sub_balance)
async def admin_subbalance(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel") or msg.text in ("❌ Bekor qilish", "❌ Cancel", "❌ Отмена"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    parts = msg.text.strip().split()
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await msg.answer("❌ Format: `<user_id> <summa>`")
        return
    uid_t, amt = int(parts[0]), int(parts[1])
    cur_bal = await get_balance(uid_t)
    new_bal = max(0, cur_bal - amt)
    deducted = cur_bal - new_bal
    await users.update_one({"user_id": uid_t}, {"$set": {"balance": new_bal}})
    user_lang = await get_user_lang(uid_t)
    try:
        await bot.send_message(uid_t, f"💸 Hisobingizdan *{deducted:,} so'm* ayirildi.\n💰 Qolgan balans: *{new_bal:,} so'm*", reply_markup=main_kb(user_lang))
    except Exception:
        pass
    await state.clear()
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    await msg.answer(f"✅ {uid_t} dan {deducted:,} so'm ayirildi.\n💰 Qolgan balans: {new_bal:,} so'm.", reply_markup=main_kb(lang))

@dp.message(Command("addbalance"))
async def cmd_addbalance(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("❌ Ruxsat yo'q!")
        return
    parts = msg.text.split()
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await msg.answer("❌ Format: /addbalance <user_id> <summa>")
        return
    uid_t, amt = int(parts[1]), int(parts[2])
    await users.update_one({"user_id": uid_t}, {"$inc": {"balance": amt}})
    user_lang = await get_user_lang(uid_t)
    try:
        await bot.send_message(uid_t, f"💰 Hisobingizga *{amt:,} so'm* qo'shildi!", reply_markup=main_kb(user_lang))
    except Exception:
        pass
    await msg.answer(f"✅ {uid_t} ga {amt:,} so'm qo'shildi.")

@dp.callback_query(F.data == "adm_bc")
async def adm_bc(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await cb.message.answer("📸 Rasm yuboring yoki o'tkazib yuboring:", reply_markup=skip_cancel_kb())
    await state.set_state(Broadcast.photo)
    await cb.answer()

@dp.message(Broadcast.photo, F.photo)
async def bc_photo(msg: types.Message, state: FSMContext):
    await state.update_data(bc_photo=msg.photo[-1].file_id)
    await msg.answer("📝 Xabar matnini yozing:", reply_markup=cancel_kb())
    await state.set_state(Broadcast.text)

@dp.message(Broadcast.photo)
async def bc_no_photo(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel") or msg.text in ("❌ Bekor qilish", "❌ Cancel", "❌ Отмена"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await state.update_data(bc_photo=None)
    await msg.answer("📝 Xabar matnini yozing:", reply_markup=cancel_kb(lang))
    await state.set_state(Broadcast.text)

@dp.message(Broadcast.text)
async def bc_text(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel") or msg.text in ("❌ Bekor qilish", "❌ Cancel", "❌ Отмена"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    d     = await state.get_data()
    text  = msg.text.strip()
    photo = d.get("bc_photo")
    await state.clear()
    uids = await all_user_ids()
    sent = 0
    for uid in uids:
        try:
            if photo:
                await bot.send_photo(uid, photo, caption=text)
            else:
                await bot.send_message(uid, text)
            sent += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    await msg.answer(f"✅ Xabar *{sent}/{len(uids)}* ta foydalanuvchiga yuborildi!", reply_markup=main_kb(lang))

# ── MUTE HANDLERS ──────────────────────────────────────
@dp.callback_query(F.data == "adm_mute")
async def adm_mute(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await cb.message.answer(
        "🔇 *Mute berish*\n\nFoydalanuvchi ID sini kiriting:",
        reply_markup=cancel_kb()
    )
    await state.set_state(MuteFlow.user_id)
    await cb.answer()

@dp.message(MuteFlow.user_id)
async def mute_get_user_id(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel") or msg.text in ("❌ Bekor qilish", "❌ Cancel", "❌ Отмена"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    txt = msg.text.strip()
    if not txt.isdigit():
        await msg.answer("❌ Faqat raqam (Telegram ID) kiriting:")
        return
    uid_target = int(txt)
    u = await get_user(uid_target)
    if not u:
        await msg.answer("❌ Bunday foydalanuvchi topilmadi.")
        return
    await state.update_data(mute_target_id=uid_target, mute_target_name=u.get("username", str(uid_target)))
    await msg.answer(
        f"✅ Foydalanuvchi: @{u.get('username', '-')} (`{uid_target}`)\n\n"
        "⏱ Necha vaqtga mute bermoqchisiz? (faqat raqam):",
        reply_markup=cancel_kb()
    )
    await state.set_state(MuteFlow.duration)

@dp.message(MuteFlow.duration)
async def mute_get_duration(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel") or msg.text in ("❌ Bekor qilish", "❌ Cancel", "❌ Отмена"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    txt = msg.text.strip()
    if not txt.isdigit() or int(txt) <= 0:
        await msg.answer("❌ Musbat raqam kiriting:")
        return
    await state.update_data(mute_duration=int(txt))
    b = InlineKeyboardBuilder()
    b.button(text="⏱ Sekund", callback_data="mute_unit_sec")
    b.button(text="🕐 Daqiqa", callback_data="mute_unit_min")
    b.button(text="⏰ Soat",   callback_data="mute_unit_hour")
    b.button(text="📅 Kun",    callback_data="mute_unit_day")
    b.adjust(2)
    await msg.answer("📏 Vaqt birligini tanlang:", reply_markup=b.as_markup())
    await state.set_state(MuteFlow.unit)

@dp.callback_query(F.data.startswith("mute_unit_"))
async def mute_set_unit(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    unit_map = {
        "mute_unit_sec":  ("sekund",  1),
        "mute_unit_min":  ("daqiqa",  60),
        "mute_unit_hour": ("soat",    3600),
        "mute_unit_day":  ("kun",     86400),
    }
    unit_label, multiplier = unit_map[cb.data]
    d = await state.get_data()
    duration    = d.get("mute_duration", 0)
    target_id   = d.get("mute_target_id")
    target_name = d.get("mute_target_name", str(target_id))

    from datetime import datetime as dt
    until_ts = dt.now().timestamp() + duration * multiplier

    await mute_user(target_id, until_ts, reason=f"Admin tomonidan mute: {duration} {unit_label}")
    await state.clear()

    user_lang = await get_user_lang(target_id)
    try:
        await bot.send_message(
            target_id,
            f"🔇 Siz {duration} {unit_label}ga *mute* oldingiz.\n"
            f"Bu vaqt ichida botdan foydalana olmaysiz."
        )
    except Exception:
        pass

    admin_lang = await get_user_lang(cb.from_user.id)
    await cb.message.answer(
        f"✅ @{target_name} (`{target_id}`) foydalanuvchiga\n"
        f"⏱ {duration} {unit_label}ga mute berildi!",
        reply_markup=main_kb(admin_lang)
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("adm_unmute_"))
async def adm_unmute(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    uid_target = int(cb.data.split("_")[2])
    await unmute_user(uid_target)
    user_lang = await get_user_lang(uid_target)
    try:
        await bot.send_message(uid_target, "✅ Mutingiz olib tashlandi! Botdan foydalanishingiz mumkin.", reply_markup=main_kb(user_lang))
    except Exception:
        pass
    try:
        await cb.message.edit_text(cb.message.text + "\n\n✅ MUTE OLIB TASHLANDI")
    except Exception:
        pass
    await cb.answer("✅ Mute olib tashlandi!")

@dp.message(Command("mute"))
async def cmd_mute(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("❌ Ruxsat yo'q!")
        return
    parts = msg.text.split()
    if len(parts) < 3:
        await msg.answer("❌ Format: /mute <user_id> <daqiqa>")
        return
    if not parts[1].isdigit() or not parts[2].isdigit():
        await msg.answer("❌ user_id va daqiqa raqam bo'lishi kerak!")
        return
    uid_target = int(parts[1])
    minutes = int(parts[2])
    from datetime import datetime as dt
    until_ts = dt.now().timestamp() + minutes * 60
    await mute_user(uid_target, until_ts)
    try:
        await bot.send_message(uid_target, f"🔇 Siz {minutes} daqiqaga *mute* oldingiz.")
    except Exception:
        pass
    await msg.answer(f"✅ {uid_target} foydalanuvchiga {minutes} daqiqa mute berildi.")

@dp.message(Command("unmute"))
async def cmd_unmute(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("❌ Ruxsat yo'q!")
        return
    parts = msg.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await msg.answer("❌ Format: /unmute <user_id>")
        return
    uid_target = int(parts[1])
    await unmute_user(uid_target)
    user_lang = await get_user_lang(uid_target)
    try:
        await bot.send_message(uid_target, "✅ Mutingiz olib tashlandi!", reply_markup=main_kb(user_lang))
    except Exception:
        pass
    await msg.answer(f"✅ {uid_target} foydalanuvchining mutesi olib tashlandi.")

# ─── Foydalanuvchilar bo'limi ──────────────────────────
USERS_PER_PAGE = 10

@dp.callback_query(F.data.startswith("adm_users_"))
async def adm_users(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    page = int(cb.data.split("_")[2])
    total = await users.count_documents({})
    skip = page * USERS_PER_PAGE
    user_list = [u async for u in users.find({}).sort("_id", -1).skip(skip).limit(USERS_PER_PAGE)]
    if not user_list:
        await cb.answer("Foydalanuvchilar yo'q!", show_alert=True)
        return
    text = f"👥 *Foydalanuvchilar* [{page * USERS_PER_PAGE + 1}–{min((page+1) * USERS_PER_PAGE, total)}/{total}]\n\n"
    b = InlineKeyboardBuilder()
    for u in user_list:
        uid_u = u["user_id"]
        uname = u.get("username") or "-"
        bal   = u.get("balance", 0)
        muted = await is_muted(uid_u)
        mute_icon = "🔇" if muted else "🔊"
        text += f"{mute_icon} `{uid_u}` | @{esc_md(uname)} | {bal:,} so'm\n"
        b.button(text=f"{mute_icon} {uid_u}", callback_data=f"adm_user_{uid_u}")
    b.adjust(2)
    nav = InlineKeyboardBuilder()
    if page > 0:
        nav.button(text="⬅️ Oldingi", callback_data=f"adm_users_{page-1}")
    if (page + 1) * USERS_PER_PAGE < total:
        nav.button(text="➡️ Keyingi", callback_data=f"adm_users_{page+1}")
    nav.button(text="🔙 Admin panel", callback_data="adm_back")
    nav.adjust(2, 1)
    combined = InlineKeyboardBuilder()
    for row in b.as_markup().inline_keyboard:
        combined.row(*[btn for btn in row])
    for row in nav.as_markup().inline_keyboard:
        combined.row(*[btn for btn in row])
    try:
        await cb.message.edit_text(text, reply_markup=combined.as_markup())
    except Exception:
        await cb.message.answer(text, reply_markup=combined.as_markup())
    await cb.answer()

@dp.callback_query(F.data.startswith("adm_user_"))
async def adm_user_detail(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    uid_target = int(cb.data.split("_")[2])
    u = await get_user(uid_target)
    if not u:
        await cb.answer("Foydalanuvchi topilmadi!", show_alert=True)
        return
    muted = await is_muted(uid_target)
    mute_rem = await mute_remaining(uid_target) if muted else "-"
    tr_count = len(await my_trades(uid_target))
    sl_count = len(await my_sales(uid_target))
    text = (
        f"👤 *Foydalanuvchi ma'lumotlari*\n\n"
        f"🆔 ID: `{uid_target}`\n"
        f"📛 Username: @{esc_md(u.get('username', '-'))}\n"
        f"💰 Balans: *{u.get('balance', 0):,} so'm*\n"
        f"📈 Jami kiritilgan: *{u.get('total_deposited', 0):,} so'm*\n"
        f"📅 Ro'yxat: {u.get('joined', '-')}\n"
        f"🔄 Faol tradelari: {tr_count}\n"
        f"🛍 Faol sotuvlari: {sl_count}\n"
        f"🔇 Mute: {'✅ Ha (' + mute_rem + ' qoldi)' if muted else '❌ Yoq'}"
    )
    b = InlineKeyboardBuilder()
    if muted:
        b.button(text="🔊 Mute olib tashlash", callback_data=f"adm_unmute_{uid_target}")
    else:
        b.button(text="🔇 Mute berish", callback_data=f"adm_mute_user_{uid_target}")
    b.button(text="💰 Balans qo'shish", callback_data=f"adm_bal_{uid_target}")
    b.button(text="➖ Balans ayirish", callback_data=f"adm_subq_{uid_target}")
    b.button(text="🔙 Orqaga", callback_data="adm_users_0")
    b.adjust(1)
    try:
        await cb.message.edit_text(text, reply_markup=b.as_markup())
    except Exception:
        await cb.message.answer(text, reply_markup=b.as_markup())
    await cb.answer()

@dp.callback_query(F.data.startswith("adm_mute_user_"))
async def adm_mute_user_quick(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    uid_target = int(cb.data.split("_")[3])
    u = await get_user(uid_target)
    target_name = u.get("username", str(uid_target)) if u else str(uid_target)
    await state.update_data(mute_target_id=uid_target, mute_target_name=target_name)
    await cb.message.answer(
        f"🔇 @{target_name} uchun mute vaqtini kiriting (faqat raqam):",
        reply_markup=cancel_kb()
    )
    await state.set_state(MuteFlow.duration)
    await cb.answer()

@dp.callback_query(F.data.startswith("adm_bal_"))
async def adm_bal_quick(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    uid_target = int(cb.data.split("_")[2])
    await state.update_data(quick_bal_uid=uid_target)
    await cb.message.answer(
        f"💰 {uid_target} foydalanuvchiga necha so'm qo'shish?\n_(raqam kiriting)_:",
        reply_markup=cancel_kb()
    )
    await state.set_state(AdminCmd.quick_add_balance)
    await cb.answer()

@dp.message(AdminCmd.quick_add_balance)
async def admin_quick_addbalance(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel") or msg.text in ("❌ Bekor qilish", "❌ Cancel", "❌ Отмена"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    txt = msg.text.strip().replace(" ", "")
    if not txt.isdigit():
        await msg.answer(T(lang, "only_number"))
        return
    d = await state.get_data()
    uid_t = d.get("quick_bal_uid")
    amt = int(txt)
    await users.update_one({"user_id": uid_t}, {"$inc": {"balance": amt}})
    user_lang = await get_user_lang(uid_t)
    try:
        await bot.send_message(uid_t, f"💰 Hisobingizga *{amt:,} so'm* qo'shildi!", reply_markup=main_kb(user_lang))
    except Exception:
        pass
    await state.clear()
    await msg.answer(f"✅ {uid_t} ga {amt:,} so'm qo'shildi.", reply_markup=main_kb(lang))

@dp.callback_query(F.data.startswith("adm_subq_"))
async def adm_subq_quick(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    uid_target = int(cb.data[len("adm_subq_"):])
    await state.update_data(quick_bal_uid=uid_target)
    await cb.message.answer(
        f"➖ {uid_target} foydalanuvchidan necha so'm ayirish?\n_(raqam kiriting)_:",
        reply_markup=cancel_kb()
    )
    await state.set_state(AdminCmd.quick_sub_balance)
    await cb.answer()

@dp.message(AdminCmd.quick_sub_balance)
async def admin_quick_subbalance(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel") or msg.text in ("❌ Bekor qilish", "❌ Cancel", "❌ Отмена"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    txt = msg.text.strip().replace(" ", "")
    if not txt.isdigit():
        await msg.answer(T(lang, "only_number"))
        return
    d = await state.get_data()
    uid_t = d.get("quick_bal_uid")
    amt = int(txt)
    cur_bal = await get_balance(uid_t)
    new_bal = max(0, cur_bal - amt)
    deducted = cur_bal - new_bal
    await users.update_one({"user_id": uid_t}, {"$set": {"balance": new_bal}})
    user_lang = await get_user_lang(uid_t)
    try:
        await bot.send_message(uid_t, f"💸 Hisobingizdan *{deducted:,} so'm* ayirildi.\n💰 Qolgan balans: *{new_bal:,} so'm*", reply_markup=main_kb(user_lang))
    except Exception:
        pass
    await state.clear()
    await msg.answer(f"✅ {uid_t} dan {deducted:,} so'm ayirildi.\n💰 Qolgan balans: {new_bal:,} so'm.", reply_markup=main_kb(lang))

@dp.callback_query(F.data == "adm_back")
async def adm_back(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    markup, cnt, or_, tr, sl = await admin_panel_kb()
    try:
        await cb.message.edit_text(
            f"🛠 *Admin Panel*\n\n👥 Foydalanuvchilar: *{cnt}*\n"
            f"📦 Kutayotgan buyurtmalar: *{len(or_)}*\n"
            f"🔄 Faol tradelar: *{len(tr)}*\n🛍 Faol sotuvlar: *{len(sl)}*",
            reply_markup=markup
        )
    except Exception:
        await cb.message.answer(f"🛠 *Admin Panel*\n\n👥 Foydalanuvchilar: *{cnt}*", reply_markup=markup)
    await cb.answer()

# ═══════════════════════════════════════════════════════
# WEBHOOK + MAIN
# ═══════════════════════════════════════════════════════
WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL", "")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL  = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEB_PORT     = int(os.getenv("PORT", 10000))


async def on_startup(bot: Bot):
    await init_indexes()
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
    logging.info(f"✅ Webhook o'rnatildi: {WEBHOOK_URL}")


async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    logging.info("🔴 Webhook o'chirildi.")


def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()

    async def health(request):
        return web.Response(text="OK")

    app.router.add_get("/", health)

    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    logging.info(f"🚀 Server port {WEB_PORT} da ishga tushdi")
    web.run_app(app, host="0.0.0.0", port=WEB_PORT)


if __name__ == "__main__":
    main()
