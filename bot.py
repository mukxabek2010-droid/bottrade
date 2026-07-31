import os
import asyncio
import logging
import base64
import hashlib
import hmac
import time
import json
from urllib.parse import parse_qsl
import requests
from io import BytesIO
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import WebAppInfo
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import aiohttp

# ── AI Yordamchi (userbot) uchun qo'shimcha kutubxonalar ──
from cryptography.fernet import Fernet
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError,
    PasswordHashInvalidError, FloodWaitError, PhoneNumberInvalidError,
    SendCodeUnavailableError,
)
from telethon.tl.types import Channel, Chat, InputPeerChannel


load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# ═══════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════
BOT_TOKEN         = os.getenv("BOT_TOKEN")
MONGO_URI         = os.getenv("MONGO_URI")

REQUIRED_CHANNELS = ["@uzbekroblox", "@trade_chanel_uz"]
TRADE_CHANNEL     = "@trade_chanel_uz"
CARD_NUMBER       = os.getenv("CARD_NUMBER", "9860080394103636")
CARD_OWNER        = os.getenv("CARD_OWNER", "Mashrapova.D")
CHAT_LINK         = os.getenv("CHAT_LINK", "https://t.me/roblox_chat_veko")
ROBLOX_SCRIPT_CHANNEL = os.getenv("ROBLOX_SCRIPT_CHANNEL", "https://t.me/deltascriptuz")

# ── Yutuqli o'yin (Telegram Web App) ──
# Render'da avtomatik beriladigan tashqi manzil (masalan: https://mybot.onrender.com)
_RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
WEBAPP_URL = os.getenv("WEBAPP_URL") or (f"{_RENDER_EXTERNAL_URL}/webapp/index.html" if _RENDER_EXTERNAL_URL else "")

# ── AI Yordamchi (foydalanuvchi Telegram akkauntini ulash) uchun ──
# my.telegram.org saytidan olinadigan API ma'lumotlari (.env ga qo'shiladi)
TELETHON_API_ID   = int(os.getenv("TELETHON_API_ID", "0") or "0")
TELETHON_API_HASH = os.getenv("TELETHON_API_HASH", "")
# Session'larni shifrlash uchun kalit. .env ga SESSION_ENCRYPT_KEY qo'ymasa,
# BOT_TOKEN asosida barqaror (lekin kamroq xavfsiz) kalit hosil qilinadi.
_SESSION_KEY_SOURCE = os.getenv("SESSION_ENCRYPT_KEY") or BOT_TOKEN or "veko_fallback_key"
_FERNET_KEY = base64.urlsafe_b64encode(hashlib.sha256(_SESSION_KEY_SOURCE.encode()).digest())
FERNET = Fernet(_FERNET_KEY)

def encrypt_session(s: str) -> str:
    return FERNET.encrypt(s.encode()).decode()

def decrypt_session(s: str) -> str:
    return FERNET.decrypt(s.encode()).decode()

ADMIN_IDS = {8866852203, 7405798326}

def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS or ADMIN_ROLES.get(uid) == "super"

ADMIN_ID = 8667862086

# ═══════════════════════════════════════════════════════
# ADMIN ROLLARI TIZIMI (Super / Referal / Robux / Mashkalar)
# ═══════════════════════════════════════════════════════
ROBUX_ADMIN_CONTACT = "@its_vekoo"

ADMIN_ROLE_LABELS = {
    "super":    "👑 Super admin",
    "referral": "🎁 Referal admin",
    "robux":    "🪙 Robux admin",
    "stock":    "📦 Stock admin",
    "bloxfruit":"🍈 Xizmatlar admin",
}

# Xotirada keshlanadigan rollar: {user_id: role}
ADMIN_ROLES: dict[int, str] = {}

async def load_admin_roles():
    global ADMIN_ROLES
    fresh = {}
    async for a in admins_col.find({}):
        fresh[a["user_id"]] = a["role"]
    ADMIN_ROLES = fresh

async def add_admin_role(uid: int, role: str):
    await admins_col.update_one({"user_id": uid}, {"$set": {"user_id": uid, "role": role}}, upsert=True)
    ADMIN_ROLES[uid] = role

async def remove_admin_role(uid: int):
    await admins_col.delete_one({"user_id": uid})
    ADMIN_ROLES.pop(uid, None)

def is_super_admin(uid: int) -> bool:
    return uid in ADMIN_IDS or ADMIN_ROLES.get(uid) == "super"

def is_referral_admin(uid: int) -> bool:
    return is_super_admin(uid) or ADMIN_ROLES.get(uid) == "referral"

def is_robux_admin(uid: int) -> bool:
    return is_super_admin(uid) or ADMIN_ROLES.get(uid) == "robux"

def is_stock_admin(uid: int) -> bool:
    return is_super_admin(uid) or ADMIN_ROLES.get(uid) == "stock"

def is_bloxfruit_admin(uid: int) -> bool:
    return is_super_admin(uid) or ADMIN_ROLES.get(uid) == "bloxfruit"

def is_any_admin(uid: int) -> bool:
    return is_super_admin(uid) or uid in ADMIN_ROLES

def get_admin_role(uid: int) -> str | None:
    if uid in ADMIN_IDS:
        return "super"
    return ADMIN_ROLES.get(uid)

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
        "btn_duel": "⚔️ Duel qo'shish",
        "btn_duel_list": "⚔️ Duel e'lonlar",
        "btn_proofs": "✅ Isbotlar",
        "btn_add_trade": "➕ Trade qo'shish",
        "btn_add_sale": "➕ Sotish qo'shish",
        "btn_trade_menu": "🔄 Trade",
        "btn_duel_menu": "⚔️ Duel",
        "btn_sotuv_menu": "🛍 Sotuv",
        "btn_accounts_menu": "👤 Akkauntlar",
        "btn_pro_menu": "💎 Pro",
        "menu_add": "➕ Qo'shish",
        "menu_view": "👀 Ko'rish",
        "acc_buy": "🛒 Akkount olish",
        "acc_sell": "💰 Akkount sotish",
        "btn_online": "🌐 Online Traderlar",
        "btn_cart": "🛒 Savat",
        "btn_ad": "📣 Reklama qilish",
        "btn_admin_service": "🛡 Trade qilib berish",
        "btn_suggest": "💡 Taklif berish",
        "btn_search": "🔍 Qidiruv",
        "btn_referral": "🎁 Referal",
        "btn_game": "🏆 Yutuqli o'yin",
        "btn_promo": "🎟 Promokod",
        "btn_change_lang": "🌐 Tilni o'zgartirish",
        "btn_bloxfruit": "🍈 Blox Fruit",
        "sub_msg": "👋 Salom! Botdan foydalanish uchun avval quyidagi kanallarga obuna bo'ling!",
        "sub_confirm": "✅ Obunani tasdiqlash",
        "not_subbed": "❌ Hali barcha kanallarga obuna bo'lmagansiz!",
        "muted_msg": "🔇 *Kechirasiz, siz adminlar tomonidan mute qilindingiz!*\n\nShuning uchun botni hozircha ishlata olmaysiz.\n\n⏳ *Mute yechilish vaqti:* {rem}",
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
        "btn_duel": "⚔️ Add Duel",
        "btn_duel_list": "⚔️ Duel Ads",
        "btn_proofs": "✅ Proofs",
        "btn_add_trade": "➕ Add Trade",
        "btn_add_sale": "➕ Add Sale",
        "btn_trade_menu": "🔄 Trade",
        "btn_duel_menu": "⚔️ Duel",
        "btn_sotuv_menu": "🛍 Sale",
        "btn_accounts_menu": "👤 Accounts",
        "btn_pro_menu": "💎 Pro",
        "menu_add": "➕ Add",
        "menu_view": "👀 View",
        "acc_buy": "🛒 Buy account",
        "acc_sell": "💰 Sell account",
        "btn_online": "🌐 Online Traders",
        "btn_cart": "🛒 Cart",
        "btn_ad": "📣 Advertise",
        "btn_admin_service": "🛡 Trade for you",
        "btn_suggest": "💡 Suggestion",
        "btn_search": "🔍 Search",
        "btn_referral": "🎁 Referral",
        "btn_game": "🏆 Lucky Game",
        "btn_promo": "🎟 Promo code",
        "btn_change_lang": "🌐 Change Language",
        "btn_bloxfruit": "🍈 Blox Fruit",
        "sub_msg": "👋 Hello! Please subscribe to all channels to use the bot!",
        "sub_confirm": "✅ Confirm Subscription",
        "not_subbed": "❌ You haven't subscribed to all channels yet!",
        "muted_msg": "🔇 *Sorry, you have been muted by admins!*\n\nYou cannot use the bot right now.\n\n⏳ *Mute ends in:* {rem}",
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
        "btn_duel": "⚔️ Добавить дуэль",
        "btn_duel_list": "⚔️ Дуэль объявления",
        "btn_proofs": "✅ Пруфы",
        "btn_add_trade": "➕ Добавить трейд",
        "btn_add_sale": "➕ Добавить продажу",
        "btn_trade_menu": "🔄 Трейд",
        "btn_duel_menu": "⚔️ Дуэль",
        "btn_sotuv_menu": "🛍 Продажа",
        "btn_accounts_menu": "👤 Аккаунты",
        "btn_pro_menu": "💎 Про",
        "menu_add": "➕ Добавить",
        "menu_view": "👀 Смотреть",
        "acc_buy": "🛒 Купить аккаунт",
        "acc_sell": "💰 Продать аккаунт",
        "btn_online": "🌐 Онлайн трейдеры",
        "btn_cart": "🛒 Корзина",
        "btn_ad": "📣 Реклама",
        "btn_admin_service": "🛡 Трейд за вас",
        "btn_suggest": "💡 Предложение",
        "btn_search": "🔍 Поиск",
        "btn_referral": "🎁 Реферал",
        "btn_game": "🏆 Игра на удачу",
        "btn_promo": "🎟 Промокод",
        "btn_change_lang": "🌐 Сменить язык",
        "btn_bloxfruit": "🍈 Blox Fruit",
        "sub_msg": "👋 Привет! Подпишитесь на все каналы, чтобы использовать бот!",
        "sub_confirm": "✅ Подтвердить подписку",
        "not_subbed": "❌ Вы ещё не подписались на все каналы!",
        "muted_msg": "🔇 *Извините, вы замучены администраторами!*\n\nВы не можете пользоваться ботом сейчас.\n\n⏳ *Мут закончится через:* {rem}",
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
admins_col     = mdb["admins"]
duels          = mdb["duels"]
settings_col   = mdb["settings"]
promocodes_col = mdb["promocodes"]      # promokodlar (bonus balans/robux)

# ── AI Yordamchi uchun kolleksiyalar ──
userbot_accounts   = mdb["userbot_accounts"]    # ulangan shaxsiy akkauntlar (session'lar shifrlangan holda)
autoreply_col      = mdb["autoreply_settings"]  # avto javob sozlamalari
autobroadcast_col  = mdb["autobroadcast"]       # avto xabar (kanallarga davriy yuborish) sozlamalari

# ── Web App Chat tizimi uchun kolleksiyalar ──
chat_global_col    = mdb["chat_global"]         # global chat xabarlari (hammaga ko'rinadi)
chat_private_col   = mdb["chat_private"]        # shaxsiy chat xabarlari (ikki foydalanuvchi orasida)
chat_contacts_col  = mdb["chat_contacts"]       # shaxsiy chat kontaktlar ro'yxati (owner_id -> peer_id)

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
    await pending_refs_db.create_index("user_id", unique=True)
    await userbot_accounts.create_index("user_id", unique=True)
    await autoreply_col.create_index("user_id", unique=True)
    await autobroadcast_col.create_index("user_id")
    await users.create_index("username_lower")
    await chat_global_col.create_index("ts")
    await chat_private_col.create_index([("from_id", 1), ("to_id", 1), ("ts", 1)])
    await chat_contacts_col.create_index([("owner_id", 1), ("peer_id", 1)], unique=True)

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
        "$set": {"username": uname, "username_lower": (uname or "").lower(), "last_seen": now()},
        "$setOnInsert": {"user_id": uid, "balance": 0, "total_deposited": 0, "joined": now(), "lang": lang}
    }
    await users.update_one({"user_id": uid}, upd, upsert=True)

async def upsert_user_profile(tg_user: dict, lang: str = "uz"):
    """Web App initData orqali kelgan foydalanuvchi profilini (ism, username, rasm)
    bazada yangilaydi. Chat tizimi shu ma'lumotlar orqali foydalanuvchini
    username bo'yicha topadi va ismi/rasmini ko'rsatadi."""
    uid = tg_user["id"]
    uname = tg_user.get("username", "") or ""
    upd = {
        "$set": {
            "username": uname,
            "username_lower": uname.lower(),
            "first_name": tg_user.get("first_name", "") or "",
            "last_name": tg_user.get("last_name", "") or "",
            "photo_url": tg_user.get("photo_url", "") or "",
            "last_seen": now(),
        },
        "$setOnInsert": {"user_id": uid, "balance": 0, "total_deposited": 0, "joined": now(), "lang": lang}
    }
    await users.update_one({"user_id": uid}, upd, upsert=True)

def display_name(u: dict) -> str:
    full = ((u.get("first_name") or "") + " " + (u.get("last_name") or "")).strip()
    return full or u.get("username") or "Foydalanuvchi"

async def find_user_by_username(username: str):
    uname = (username or "").strip().lstrip("@").lower()
    if not uname:
        return None
    return await users.find_one({"username_lower": uname})

async def ensure_chat_contact(owner_id: int, peer_id: int):
    await chat_contacts_col.update_one(
        {"owner_id": owner_id, "peer_id": peer_id},
        {"$setOnInsert": {"owner_id": owner_id, "peer_id": peer_id, "created_at": now()}},
        upsert=True
    )

async def finalize_referral(uid: int, state: FSMContext):
    """Bazada saqlangan pending referal bo'lsa, foydalanuvchi hali ro'yxatdan
    o'tmagan (yangi) bo'lsa va referal hali biriktirilmagan bo'lsa - referalni yakunlaydi.
    Bu funksiya /start, tilni tanlash va 'obunani tasdiqlash' bosqichlarining hammasida
    chaqiriladi, shunda obunaga o'tib keyin qaytgan foydalanuvchilar uchun ham referal ishlaydi.
    Eslatma: bu ma'lumot MongoDB'da saqlanadi (FSM xotirasida emas), shuning uchun bot
    qayta ishga tushsa ham (Render uyqu holati va h.k.) referal yo'qolmaydi."""
    pending = await pending_refs_db.find_one({"user_id": uid})
    ref_uid = pending.get("ref_uid") if pending else None
    if not ref_uid or ref_uid == uid:
        return
    existing_user = await get_user(uid)
    if existing_user:
        await pending_refs_db.delete_one({"user_id": uid})
        return
    already = await get_referrer(uid)
    if already:
        await pending_refs_db.delete_one({"user_id": uid})
        return
    inviter = await get_user(ref_uid)
    if not inviter:
        await pending_refs_db.delete_one({"user_id": uid})
        return
    await set_referrer(uid, ref_uid)
    await add_ref(ref_uid)
    inviter_lang = inviter.get("lang", "uz")
    try:
        ref_total = await get_ref_count(ref_uid)
        await bot.send_message(
            ref_uid,
            f"🎉 *Yangi referal qo'shildi!*\n\n"
            f"👤 Siz taklif qilgan odam botga kirdi.\n"
            f"🎁 Jami refallaringiz: *{ref_total}* ta",
            reply_markup=main_kb(inviter_lang)
        )
    except Exception:
        pass
    await pending_refs_db.delete_one({"user_id": uid})

async def get_balance(uid):
    u = await users.find_one({"user_id": uid}, {"balance": 1})
    return u["balance"] if u else 0

async def add_balance(uid, amt):
    await users.update_one({"user_id": uid}, {"$inc": {"balance": amt, "total_deposited": amt}})

async def sub_balance(uid, amt):
    await users.update_one({"user_id": uid}, {"$inc": {"balance": -amt}})

async def add_win_balance(uid, amt):
    """Web App o'yinidagi yutuqlarni balansga qo'shadi (total_deposited ga tegmaydi)."""
    await users.update_one({"user_id": uid}, {"$inc": {"balance": amt}})

# ═══════════════════════════════════════════════════════
# TELEGRAM WEB APP — initData tekshiruvi (xavfsizlik uchun)
# ═══════════════════════════════════════════════════════
def verify_webapp_initdata(init_data: str):
    """Telegram tomonidan yuborilgan initData ni HMAC orqali tekshiradi.
    Muvaffaqiyatli bo'lsa foydalanuvchi dict'ini qaytaradi, aks holda None."""
    if not init_data or not BOT_TOKEN:
        return None
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        recv_hash = parsed.pop("hash", None)
        if not recv_hash:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc_hash, recv_hash):
            return None
        auth_date = int(parsed.get("auth_date", 0))
        if time.time() - auth_date > 86400:
            return None
        user_json = parsed.get("user")
        if not user_json:
            return None
        return json.loads(user_json)
    except Exception:
        return None

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
    robux_credited = 0
    if dep:
        await deposits.update_one({"_id": ObjectId(str(did))}, {"$set": {"status": "approved"}})
        await users.update_one({"user_id": dep["user_id"]}, {"$inc": {"balance": dep["amount"], "total_deposited": dep["amount"]}})
        # Hisob to'ldirilganda avtomatik Robux bonus (admin panelda sozlanadigan kurs bo'yicha)
        rate = await get_robux_rate()
        robux_credited = round(dep["amount"] * rate, 4)
        if robux_credited > 0:
            await add_robux(dep["user_id"], robux_credited)
    return robux_credited

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

# duels
async def add_duel(uid, uname, nick, bio, photo_id):
    r = await duels.insert_one({
        "user_id": uid, "username": uname, "roblox_nick": nick,
        "bio": bio, "photo_id": photo_id,
        "status": "active", "created_at": now()
    })
    return r.inserted_id

async def get_duel(did):
    return await duels.find_one({"_id": ObjectId(str(did))})

async def active_duels():
    return [d async for d in duels.find({"status": "active"}).sort("_id", -1)]

async def my_duels(uid):
    return [d async for d in duels.find({"user_id": uid, "status": "active"}).sort("_id", -1)]

async def delete_duel(did):
    await duels.update_one({"_id": ObjectId(str(did))}, {"$set": {"status": "deleted"}})

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
# REFERRAL DB HELPERS
# ═══════════════════════════════════════════════════════
referrals_db = mdb["referrals"]
private_orders_db = mdb["private_orders"]
pending_refs_db = mdb["pending_refs"]

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
    (1000, 130000), (2000, 255000),
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
# VALYUTA TIZIMI — barcha narxlar bazada SO'M (UZS) da saqlanadi.
# Til o'zgarganda foydalanuvchiga real kurs bo'yicha qayta hisoblab ko'rsatiladi:
#   uz -> so'm (UZS), ru -> rubl (RUB), en -> dollar (USD)
# Kurslarni admin panel orqali yangilash mumkin (adm_rates), yoki shu yerdan qo'lda.
# ═══════════════════════════════════════════════════════
CURRENCY_RATES = {
    # 1 birlik shu valyuta = necha so'm
    "UZS": 1.0,
    "USD": 12700.0,   # 1 USD ≈ 12700 so'm (taxminiy, admin panelda yangilanadi)
    "RUB": 155.0,      # 1 RUB ≈ 155 so'm (taxminiy, admin panelda yangilanadi)
}

LANG_CURRENCY = {
    "uz": "UZS",
    "ru": "RUB",
    "en": "USD",
}

CURRENCY_SYMBOL = {
    "UZS": "so'm",
    "RUB": "₽",
    "USD": "$",
}

async def get_currency_rates() -> dict:
    """MongoDB'dagi 'settings' kolleksiyasidan kurslarni o'qiydi, bo'lmasa default qiymatlarni qaytaradi."""
    try:
        doc = await settings_col.find_one({"_id": "currency_rates"})
        if doc:
            rates = dict(CURRENCY_RATES)
            rates.update({k: v for k, v in doc.items() if k in ("USD", "RUB")})
            return rates
    except Exception:
        pass
    return CURRENCY_RATES

async def set_currency_rate(code: str, rate: float):
    await settings_col.update_one(
        {"_id": "currency_rates"},
        {"$set": {code: rate}},
        upsert=True
    )
    CURRENCY_RATES[code] = rate

def _convert_uzs(amount_uzs: float, target_code: str, rates: dict) -> float:
    rate = rates.get(target_code, 1.0)
    if rate <= 0:
        rate = 1.0
    return amount_uzs / rate

async def format_money(amount_uzs: float, lang: str) -> str:
    """Bazaviy so'm miqdorini foydalanuvchi tili valyutasiga o'girib, formatlangan matn qaytaradi."""
    code = LANG_CURRENCY.get(lang, "UZS")
    if code == "UZS":
        return f"{int(round(amount_uzs)):,} so'm"
    rates = await get_currency_rates()
    val = _convert_uzs(amount_uzs, code, rates)
    symbol = CURRENCY_SYMBOL.get(code, code)
    if code == "USD":
        return f"${val:,.2f}"
    return f"{val:,.2f} {symbol}"

def format_money_sync(amount_uzs: float, lang: str, rates: dict | None = None) -> str:
    """format_money ning sync (DB so'ramaydigan) versiyasi — rates oldindan olingan bo'lsa ishlatiladi."""
    code = LANG_CURRENCY.get(lang, "UZS")
    if code == "UZS":
        return f"{int(round(amount_uzs)):,} so'm"
    rates = rates or CURRENCY_RATES
    val = _convert_uzs(amount_uzs, code, rates)
    symbol = CURRENCY_SYMBOL.get(code, code)
    if code == "USD":
        return f"${val:,.2f}"
    return f"{val:,.2f} {symbol}"

# ═══════════════════════════════════════════════════════
# ROBUX HAMYON TIZIMI (profildagi 2-chi valyuta)
# Hisob to'ldirish tasdiqlanganda va saytdagi almashtirish tugmasi orqali
# foydalanuvchi balansi (so'm) avtomatik Robux'ga aylantiriladi.
# Kurs: "necha so'mga 1 Robux to'g'ri keladi" emas, aksincha
# "1000 so'mga necha Robux tushishi" — admin panelda sozlanadi.
# ═══════════════════════════════════════════════════════
DEFAULT_ROBUX_RATE = 0.00001  # 1 so'm uchun robux miqdori (1000 so'm -> 0.01 Robux)

async def get_robux_rate() -> float:
    """1 so'm uchun necha Robux berilishini qaytaradi (bazadan, bo'lmasa default)."""
    try:
        doc = await settings_col.find_one({"_id": "robux_rate"})
        if doc and doc.get("rate"):
            return float(doc["rate"])
    except Exception:
        pass
    return DEFAULT_ROBUX_RATE

async def set_robux_rate(rate_per_1000: float):
    """Admin panelda '1000 so'mga necha Robux' shaklida kiritiladi, ichkarida 1 so'mlik kursga aylantirib saqlanadi."""
    rate_per_unit = rate_per_1000 / 1000
    await settings_col.update_one({"_id": "robux_rate"}, {"$set": {"rate": rate_per_unit}}, upsert=True)

async def get_robux_balance(uid) -> float:
    u = await users.find_one({"user_id": uid}, {"robux_balance": 1})
    return (u or {}).get("robux_balance", 0) or 0

async def add_robux(uid, amt):
    if amt == 0:
        return
    await users.update_one({"user_id": uid}, {"$inc": {"robux_balance": amt}}, upsert=True)

async def sub_robux(uid, amt):
    await users.update_one({"user_id": uid}, {"$inc": {"robux_balance": -amt}})

def fmt_robux(amt) -> str:
    amt = float(amt or 0)
    if amt == int(amt):
        return f"{int(amt):,}"
    return f"{amt:,.4f}".rstrip("0").rstrip(".")

# ═══════════════════════════════════════════════════════
# PROMOKODLAR TIZIMI
# Har bir promokod: kodi, valyutasi (so'm yoki robux), miqdori va
# nechta odam ishlata olishi (max_uses) admin tomonidan belgilanadi.
# Bir foydalanuvchi bir promokodni faqat bir marta ishlata oladi.
# ═══════════════════════════════════════════════════════
async def create_promo(code: str, currency: str, amount: float, max_uses: int, created_by: int):
    code = code.strip().upper()
    doc = {
        "code": code,
        "currency": currency,          # "uzs" | "robux"
        "amount": amount,
        "max_uses": max_uses,
        "used_count": 0,
        "used_users": [],
        "active": True,
        "created_by": created_by,
        "created_at": now(),
    }
    await promocodes_col.update_one({"code": code}, {"$set": doc}, upsert=True)
    return doc

async def get_promo(code: str):
    return await promocodes_col.find_one({"code": code.strip().upper()})

async def list_promos():
    return await promocodes_col.find({}).sort("created_at", -1).to_list(length=200)

async def delete_promo(code: str) -> bool:
    r = await promocodes_col.delete_one({"code": code.strip().upper()})
    return r.deleted_count > 0

async def redeem_promo(uid: int, code: str) -> dict:
    """Promokodni foydalanuvchi nomidan ishlatishga urinadi (atomik tekshiruv bilan)."""
    code = code.strip().upper()
    promo = await promocodes_col.find_one({"code": code})
    if not promo or not promo.get("active", True):
        return {"status": "not_found"}
    if uid in promo.get("used_users", []):
        return {"status": "already_used"}
    if promo.get("used_count", 0) >= promo.get("max_uses", 0):
        return {"status": "limit_reached"}
    upd = await promocodes_col.find_one_and_update(
        {"code": code, "active": True, "used_count": {"$lt": promo["max_uses"]}, "used_users": {"$ne": uid}},
        {"$inc": {"used_count": 1}, "$push": {"used_users": uid}}
    )
    if not upd:
        return {"status": "limit_reached"}
    currency = promo.get("currency", "uzs")
    amount = promo.get("amount", 0)
    if currency == "robux":
        await add_robux(uid, amount)
    else:
        await users.update_one({"user_id": uid}, {"$inc": {"balance": amount, "total_deposited": amount}})
    return {"status": "ok", "currency": currency, "amount": amount}

# ═══════════════════════════════════════════════════════
# BLOX FRUIT BO'LIMI (Stock + Xizmatlar) — sozlamalar
# ═══════════════════════════════════════════════════════
DEFAULT_BF_STOCK_CHANNEL = "https://t.me/deltauzbrb"

BF_SERVICES = [
    ("bf_lvl",     "🆙 Lvl ko'tarib berish"),
    ("bf_money",   "💰 Pul ko'paytirib berish"),
    ("bf_raid",    "🛡 Raidlardan o'tib berish"),
    ("bf_fruit",   "🍈 Fruit sotiladi"),
    ("bf_storage", "📦 1+ Storage"),
]

BF_SERVICES_TEXT = {
    "bf_lvl":     "🆙 *Lvl ko'tarib berish*\n\nAkkingizga kirib o'tirmaymiz — faqat natijani topshiramiz. Xohlagan levelgacha ko'tarib beramiz.",
    "bf_money":   "💰 *Pul ko'paytirib berish*\n\nO'yin ichi valyutangizni tez va xavfsiz ko'paytirib beramiz.",
    "bf_raid":    "🛡 *Raidlardan o'tib berish*\n\nEng qiyin raid/bosslardan sizning o'rningizga o'tib beramiz.",
    "bf_fruit":   "🍈 *Fruit sotiladi*\n\nXohlagan Blox Fruit turini sotib olishingiz mumkin.",
    "bf_storage": "📦 *1+ Storage*\n\nQo'shimcha storage slotlarini oshirib beramiz.",
}

async def get_bf_stock_channel() -> str:
    try:
        doc = await settings_col.find_one({"_id": "bf_stock_channel"})
        if doc and doc.get("url"):
            return doc["url"]
    except Exception:
        pass
    return DEFAULT_BF_STOCK_CHANNEL

async def set_bf_stock_channel(url: str):
    await settings_col.update_one({"_id": "bf_stock_channel"}, {"$set": {"url": url}}, upsert=True)

async def remove_sticker(event_key: str):
    await settings_col.update_one({"_id": "stickers"}, {"$unset": {event_key: ""}})

# Admin panelda boshqarish mumkin bo'lgan bo'limlar ro'yxati: (event_key, label)
STICKER_SECTIONS = [
    ("start",         "🚀 /start (xush kelibsiz xabari)"),
    ("buy",           "🛒 Robux sotib olish"),
    ("deposit",       "💰 Hisob to'ldirish"),
    ("trades",        "🔄 Tradelar"),
    ("sales",         "📊 Sotuvlar"),
    ("duel_list",     "⚔️ Duel e'lonlar"),
    ("online",        "🌐 Online Traderlar"),
    ("referral",      "🎁 Referal"),
    ("proofs",        "✅ Isbotlar"),
    ("bloxfruit",     "🍈 Blox Fruit"),
    ("roblox_script", "🎮 Roblox Skript"),
]

# ═══════════════════════════════════════════════════════
# STIKERLAR TIZIMI — masalan /start uchun stiker
# ═══════════════════════════════════════════════════════
async def get_sticker(event_key: str) -> str | None:
    try:
        doc = await settings_col.find_one({"_id": "stickers"})
        if doc:
            return doc.get(event_key)
    except Exception:
        pass
    return None

async def set_sticker(event_key: str, file_id: str):
    await settings_col.update_one({"_id": "stickers"}, {"$set": {event_key: file_id}}, upsert=True)

async def send_event_sticker(chat_id: int, event_key: str):
    """Agar shu event uchun stiker o'rnatilgan bo'lsa yuboradi, bo'lmasa hech narsa qilmaydi."""
    sid = await get_sticker(event_key)
    if sid:
        try:
            await bot.send_sticker(chat_id, sid)
        except Exception as e:
            logging.warning(f"Stiker yuborishda xato ({event_key}): {e}")

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

class DuelAdd(StatesGroup):
    photo = State()
    nick  = State()
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

class AdminRoleAdd(StatesGroup):
    user_id = State()

class PromoRedeem(StatesGroup):
    code = State()

class PromoCreate(StatesGroup):
    code     = State()
    currency = State()
    amount   = State()
    max_uses = State()

class PromoDelete(StatesGroup):
    code = State()

class RobuxRateEdit(StatesGroup):
    rate = State()

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

class RateEdit(StatesGroup):
    usd = State()
    rub = State()

class BFOrder(StatesGroup):
    nick = State()

class StickerSet(StatesGroup):
    waiting = State()

class StockEdit(StatesGroup):
    url = State()

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
# ISBOTLAR KANALI
# ═══════════════════════════════════════════════════════
PROOFS_CHANNEL = os.getenv("PROOFS_CHANNEL", "@veko_bulldrop")

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
    b.button(text=T(lang, "btn_trade_menu"))
    b.button(text=T(lang, "btn_duel_menu"))
    b.button(text=T(lang, "btn_sotuv_menu"))
    b.button(text=T(lang, "btn_accounts_menu"))
    b.button(text=T(lang, "btn_online"))
    b.button(text=T(lang, "btn_cart"))
    b.button(text=T(lang, "btn_ad"))
    b.button(text=T(lang, "btn_admin_service"))
    b.button(text=T(lang, "btn_suggest"))
    b.button(text=T(lang, "btn_search"))
    b.button(text=T(lang, "btn_roblox_script"))
    b.button(text=T(lang, "btn_proofs"))
    b.button(text=T(lang, "btn_bloxfruit"))
    b.button(text="🤖 AI Yordamchi")
    b.button(text=T(lang, "btn_pro_menu"))
    b.button(text=T(lang, "btn_change_lang"))
    b.button(text=T(lang, "btn_game"))
    b.button(text=T(lang, "btn_promo"))
    b.adjust(2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1)
    return b.as_markup(resize_keyboard=True)

def _as_user_msg(cb: types.CallbackQuery) -> types.Message:
    """Callback query'dagi xabarni asl foydalanuvchi (cb.from_user) nomidan
    yuborilgandek qilib beradi — eski message-based handlerlarni callback
    orqali qayta ishlatish uchun."""
    return cb.message.model_copy(update={"from_user": cb.from_user})

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
            err = str(e).lower()
            # Agar xato foydalanuvchi haqiqatan a'zo emasligidan bo'lsa - obuna yo'q deb hisoblaymiz
            if "user not found" in err or "user_not_participant" in err or "chat not found" in err:
                logging.warning(f"Sub check ({ch}): foydalanuvchi topilmadi/a'zo emas -> {e}")
                missing.append(ch)
            else:
                # Bot kanalda admin emas yoki boshqa texnik xato - foydalanuvchini
                # noto'g'ri bloklamaslik uchun bu kanalni tekshiruvdan o'tkazib yuboramiz,
                # lekin adminlarga log orqali xabar beramiz
                logging.error(f"⚠️ Sub check texnik xato ({ch}), foydalanuvchi bloklanmadi: {e}")
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

async def notify_role_admins(role: str, text: str, photo_id=None, markup=None):
    """Faqat asosiy (super) adminlar va shu rolga ega adminlarga xabar yuboradi."""
    targets = set(ADMIN_IDS)
    for uid, r in ADMIN_ROLES.items():
        if r == "super" or r == role:
            targets.add(uid)
    for aid in targets:
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

async def post_duel_to_channel(uname: str, nick: str, bio: str, photo_id=None):
    caption = (
        "⚔️ *YANGI DUEL E'LON*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"1️⃣ *Foydalanuvchi:* @{esc_md(uname)}\n\n"
        f"2️⃣ *Roblox nik:*\n{esc_md(nick)}\n\n"
        f"3️⃣ *Bio:*\n{esc_md(bio or '—')}\n\n"
        "4️⃣ ⚔️ *Duel*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 Murojaat: @{esc_md(uname)}"
    )
    b = InlineKeyboardBuilder()
    b.button(text="💬 Murojaat", url=f"https://t.me/{uname}")
    try:
        if photo_id:
            await bot.send_photo(TRADE_CHANNEL, photo_id, caption=caption, reply_markup=b.as_markup())
        else:
            await bot.send_message(TRADE_CHANNEL, caption, reply_markup=b.as_markup())
    except Exception as e:
        logging.error(f"Kanalga duel yuborishda xato: {e}")

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
    await send_event_sticker(msg.chat.id, "start")
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

    if ref_uid:
        # Obunaga o'tib qaytishi mumkin bo'lgani uchun referalni MongoDB'da saqlab qo'yamiz
        # (FSM xotirasi emas — bot qayta ishga tushsa ham yo'qolmasligi uchun).
        # Faqat foydalanuvchi hali ro'yxatdan o'tmagan bo'lsa va pending yozuv bo'lmasa yozamiz.
        existing_user = await get_user(uid)
        if not existing_user:
            await pending_refs_db.update_one(
                {"user_id": uid},
                {"$setOnInsert": {"user_id": uid, "ref_uid": ref_uid}},
                upsert=True
            )

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

    # Yangi foydalanuvchi bo'lsa va referal bo'lsa - endi finalize_referral orqali,
    # bu obunaga o'tib qaytgan foydalanuvchilar uchun ham ishlaydi
    await finalize_referral(uid, state)

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
    await finalize_referral(uid, state)
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
    await finalize_referral(uid, state)
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
    bal_str = await format_money(u.get('balance', 0), lang)
    dep_str = await format_money(u.get('total_deposited', 0), lang)
    robux_bal = await get_robux_balance(uid)
    await msg.answer(
        f"👤 **Profilingiz**\n\n"
        f"🆔 ID: `{uid}`\n"
        f"💰 Balans: **{bal_str}**\n"
        f"🪙 Robux: **{fmt_robux(robux_bal)}**\n"
        f"📈 Jami kiritilgan: **{dep_str}**\n"
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
# PROMOKODLAR — foydalanuvchi tomoni
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_promo") for l in LANGS)))
async def cmd_promo(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    await msg.answer(
        "🎟 *Promokodni kiriting:*\n\n"
        "Promokod orqali balansingizga bonus so'm yoki Robux qo'shilishi mumkin.",
        reply_markup=cancel_kb(lang)
    )
    await state.set_state(PromoRedeem.code)

@dp.message(PromoRedeem.code)
async def promo_redeem_handler(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    code = (msg.text or "").strip()
    if not code:
        await msg.answer("❌ Promokodni matn ko'rinishida yuboring:")
        return
    result = await redeem_promo(uid, code)
    await state.clear()
    status = result["status"]
    if status == "ok":
        currency = result["currency"]
        amount   = result["amount"]
        if currency == "robux":
            await msg.answer(
                f"🎉 *Promokod muvaffaqiyatli ishlatildi!*\n\n"
                f"🪙 Hisobingizga *{fmt_robux(amount)} Robux* qo'shildi!",
                reply_markup=main_kb(lang)
            )
        else:
            amt_str = await format_money(amount, lang)
            await msg.answer(
                f"🎉 *Promokod muvaffaqiyatli ishlatildi!*\n\n"
                f"💰 Hisobingizga *{amt_str}* qo'shildi!",
                reply_markup=main_kb(lang)
            )
    elif status == "already_used":
        await msg.answer("⚠️ Siz bu promokodni allaqachon ishlatgansiz.", reply_markup=main_kb(lang))
    elif status == "limit_reached":
        await msg.answer("⚠️ Bu promokodning ishlatilish limiti tugagan.", reply_markup=main_kb(lang))
    else:
        await msg.answer("❌ Bunday promokod topilmadi yoki faol emas. Qaytadan tekshirib ko'ring.", reply_markup=main_kb(lang))

# ═══════════════════════════════════════════════════════
# HISOB TO'LDIRISH
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_deposit") for l in LANGS)))
async def cmd_deposit(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid = msg.from_user.id
    await send_event_sticker(msg.chat.id, "deposit")
    lang = await get_user_lang(uid)
    rates = await get_currency_rates()
    b = InlineKeyboardBuilder()
    for amt in DEPOSIT_OPTIONS:
        label = f"{amt:,} so'm"
        if lang != "uz":
            label += f" ({format_money_sync(amt, lang, rates)})"
        b.button(text=label, callback_data=f"damt_{amt}")
    b.button(text="✏️ Boshqa miqdor", callback_data="damt_custom")
    b.adjust(2)
    await msg.answer("💰 *Hisob to'ldirish*\n\n📌 To'lov karta orqali FAQAT so'mda qabul qilinadi (qavs ichida taxminiy ekvivalent ko'rsatilgan).\n\nQancha to'ldirmoqchisiz?", reply_markup=b.as_markup())

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
    await _show_card(cb.message, amount, lang)
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
    await _show_card(msg, amount, lang)

async def _show_card(target, amount: int, lang: str = "uz"):
    b = InlineKeyboardBuilder()
    b.button(text="✅ To'lov qildim", callback_data="dep_paid")
    b.button(text="❌ Bekor qilish",  callback_data="dep_cancel")
    b.adjust(1)
    card_display = CARD_NUMBER.replace("-", "").replace(" ", "")
    card_display = " ".join([card_display[i:i+4] for i in range(0, len(card_display), 4)])
    amount_line = f"💰 Miqdor: *{amount:,} so'm*"
    if lang != "uz":
        eq = await format_money(amount, lang)
        amount_line += f" (≈ {eq})"
    text = (
        f"💳 *To'lov ma'lumotlari*\n\n"
        f"{amount_line}\n\n"
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
    robux_credited = await approve_deposit(did)
    user_lang = await get_user_lang(dep["user_id"])
    amt_str = await format_money(dep['amount'], user_lang)
    bonus_line = f"\n🪙 Bonus: *{fmt_robux(robux_credited)} Robux*" if robux_credited > 0 else ""
    try:
        await bot.send_message(dep["user_id"], f"✅ To'lovingiz tasdiqlandi!\n💰 *{amt_str}* hisobingizga qo'shildi!{bonus_line}", reply_markup=main_kb(user_lang))
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
    await send_event_sticker(msg.chat.id, "buy")
    lang = await get_user_lang(uid)
    bal = await get_balance(uid)
    rates = await get_currency_rates()
    b = InlineKeyboardBuilder()
    for r, p in ROBUX_PRICES:
        b.button(text=f"**{r}** Rbx — {format_money_sync(p, lang, rates)}", callback_data=f"buy_{r}")
    b.adjust(3)
    # Roblox Plus tugmalari
    b.button(text="━━━━ 🌟 Roblox Plus ━━━━", callback_data="plus_noop")
    for key, label, price in ROBLOX_PLUS_OPTIONS:
        b.button(text=f"✨ {label} — {format_money_sync(price, lang, rates)}", callback_data=f"buyplus_{key}")
    b.button(text=f"🆓 Free Trial — {format_money_sync(FREE_TRIAL_PRICE, lang, rates)}", callback_data="buy_freetrial")
    b.adjust(3, 3, 3, 3, 1, 1, 1, 1, 1, 1)
    bal_str = format_money_sync(bal, lang, rates)
    await msg.answer(
        f"🌟 **Assalomu alaykum!**\n"
        f"💰 Balansingiz: **{bal_str}**\n\n"
        f"📊 **ROBUX NARXLARI (PAKETLAR):**\n\n"
        f"👇 Quyidagilardan birini tanlang:",
        reply_markup=b.as_markup()
    )

# ── Roblox Plus / Free Trial: hozircha to'g'ridan-to'g'ri admin orqali ────
@dp.callback_query(F.data == "plus_noop")
async def cb_plus_noop(cb: types.CallbackQuery):
    await cb.answer()

@dp.callback_query(F.data.startswith("buyplus_"))
async def cb_buyplus_redirect(cb: types.CallbackQuery):
    key = cb.data[len("buyplus_"):]
    info = plus_price_for(key)
    label, price = info if info else ("Roblox Plus", 0)
    b = InlineKeyboardBuilder()
    b.button(text="💬 Admin bilan bog'lanish", url=f"https://t.me/{ROBUX_ADMIN_CONTACT.lstrip('@')}")
    b.adjust(1)
    await cb.message.answer(
        f"✨ *{label}* — {price:,} so'm\n\n"
        f"⚠️ Bu xizmat hozircha avtomatik tarzda ishlamaydi.\n"
        f"Buyurtma berish uchun adminga murojaat qiling: {ROBUX_ADMIN_CONTACT}",
        reply_markup=b.as_markup()
    )
    await cb.answer()

@dp.callback_query(F.data == "buy_freetrial")
async def cb_buy_freetrial_redirect(cb: types.CallbackQuery):
    b = InlineKeyboardBuilder()
    b.button(text="💬 Admin bilan bog'lanish", url=f"https://t.me/{ROBUX_ADMIN_CONTACT.lstrip('@')}")
    b.adjust(1)
    await cb.message.answer(
        f"🆓 *Free Trial* — {FREE_TRIAL_PRICE:,} so'm\n\n"
        f"⚠️ Bu xizmat hozircha avtomatik tarzda ishlamaydi.\n"
        f"Buyurtma berish uchun adminga murojaat qiling: {ROBUX_ADMIN_CONTACT}",
        reply_markup=b.as_markup()
    )
    await cb.answer()

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
        need_str = await format_money(price, lang)
        bal_str = await format_money(bal, lang)
        await cb.answer(f"❌ Hisobingiz yetarli emas!\nKerak: {need_str}\nBalans: {bal_str}", show_alert=True)
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
    price_str = await format_money(d['buy_price'], lang)
    await msg.answer(
        f"📋 *Ma'lumotlarni tekshiring*\n\n"
        f"🎮 Nik: `{esc_md(d['buy_nick'])}`\n"
        f"🪙 Robux: *{d['buy_robux']}*\n"
        f"💵 Narx: *{price_str}*\n"
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
        need_str = await format_money(price, lang)
        bal_str = await format_money(bal, lang)
        await cb.answer(f"❌ Hisobingiz yetarli emas!\nKerak: {need_str}\nBalans: {bal_str}", show_alert=True)
        await state.clear()
        return
    await sub_balance(uid, price)
    oid = await add_order(uid, cb.from_user.username or "user", nick, robux, price, mood)
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"ook_{oid}")
    b.button(text="❌ Rad etish", callback_data=f"ono_{oid}")
    b.adjust(2)
    # Admin xabarlari doim so'mda (do'kon egasining ish valyutasi)
    await notify_role_admins(
        "robux",
        f"🛒 *Robux buyurtma #{short_id(oid)}*\n\n"
        f"1️⃣ Nik: `{esc_md(nick)}`\n"
        f"2️⃣ Robux: *{robux}*\n"
        f"3️⃣ Narx: *{price:,} so'm*\n"
        f"4️⃣ Parol: {esc_md(mood)}\n\n"
        f"👤 @{esc_md(cb.from_user.username or '-')} (`{uid}`)\n🕐 {now()}",
        markup=b.as_markup()
    )
    await state.clear()
    price_str = await format_money(price, lang)
    await cb.message.answer(
        f"✅ *Buyurtmangiz qabul qilindi!*\n\n"
        f"🪙 Robux: *{robux}*\n"
        f"💵 To'langan: *{price_str}*\n"
        f"🎮 Nik: `{esc_md(nick)}`\n"
        f"📋 Buyurtma #{short_id(oid)}\n\n"
        f"😴 Admin tasdiqlagunicha 2 step ochirib qoyib kutib turing.",
        reply_markup=main_kb(lang)
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("ook_"))
async def cb_ook(cb: types.CallbackQuery):
    if not is_robux_admin(cb.from_user.id):
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
    if not is_robux_admin(cb.from_user.id):
        return
    oid = cb.data.split("_")[1]
    o   = await get_order(oid)
    if not o or o["status"] != "pending":
        await cb.answer("Allaqachon ko'rilgan!", show_alert=True)
        return
    await reject_order(oid)
    user_lang = await get_user_lang(o["user_id"])
    refund_str = await format_money(o['price_sum'], user_lang)
    try:
        await bot.send_message(o["user_id"], f"❌ Rad etildi.\n📋 Buyurtma #{short_id(ObjectId(str(oid)))}\n💰 {refund_str} hisobingizga qaytarildi.", reply_markup=main_kb(user_lang))
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
    await send_event_sticker(msg.chat.id, "trades")
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

# ── Duel e'lonlar ro'yxati ─────────────────────────────
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_duel_list") for l in LANGS)))
async def cmd_duel_list(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid   = msg.from_user.id
    await send_event_sticker(msg.chat.id, "duel_list")
    lang  = await get_user_lang(uid)
    items = await active_duels()
    if not items:
        await msg.answer("⚔️ Hozircha faol duel e'lonlar yo'q.\n\n➕ *Duel qo'shish* tugmasini bosing!", reply_markup=main_kb(lang))
        return
    await _send_duel_page(msg, items, 0, lang=lang, is_cb=False)

async def _send_duel_page(target, items, page, is_cb=True, lang="uz"):
    d = items[page]
    caption = (
        f"⚔️ *DUEL E'LON #{short_id(d['_id'])}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"[{page+1}/{len(items)}]\n\n"
        f"👤 @{esc_md(d.get('username', '-'))}\n\n"
        f"🎮 *Nik:* `{esc_md(d.get('roblox_nick',''))}`\n\n"
        f"📝 {esc_md(d.get('bio') or '—')}\n\n"
        f"📅 {d['created_at']}\n━━━━━━━━━━━━━━━━━━━━"
    )
    b = InlineKeyboardBuilder()
    if page > 0:
        b.button(text=T(lang, "prev"), callback_data=f"dlp_{page-1}")
    if page < len(items) - 1:
        b.button(text=T(lang, "next"), callback_data=f"dlp_{page+1}")
    uname = d.get("username", "")
    if uname:
        b.button(text=T(lang, "contact_btn"), url=f"https://t.me/{uname}")
    b.adjust(2, 1)
    if is_cb:
        await _send_or_edit(target, d.get("photo_id"), caption, b.as_markup())
    else:
        if d.get("photo_id"):
            await target.answer_photo(d["photo_id"], caption=caption, reply_markup=b.as_markup())
        else:
            await target.answer(caption, reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("dlp_"))
async def cb_dlp(cb: types.CallbackQuery):
    uid   = cb.from_user.id
    lang  = await get_user_lang(uid)
    page  = int(cb.data[len("dlp_"):])
    items = await active_duels()
    if not items:
        await cb.answer("Duel e'lonlar yo'q!", show_alert=True)
        return
    page = max(0, min(page, len(items) - 1))
    await _send_duel_page(cb, items, page, lang=lang)
    await cb.answer()

# ── Duel qo'shish ───────────────────────────────────────
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_duel") for l in LANGS)))
async def cmd_duel_add(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    await msg.answer("⚔️ Nima duel qilmoqchisiz? Rasmi:", reply_markup=skip_cancel_kb(lang))
    await state.set_state(DuelAdd.photo)

@dp.message(DuelAdd.photo, F.photo)
async def duel_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    await state.update_data(d_photo=msg.photo[-1].file_id)
    await msg.answer("🎮 Roblox nikingizni kiriting:", reply_markup=cancel_kb(lang))
    await state.set_state(DuelAdd.nick)

@dp.message(DuelAdd.photo)
async def duel_no_photo(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await state.update_data(d_photo=None)
    await msg.answer("🎮 Roblox nikingizni kiriting:", reply_markup=cancel_kb(lang))
    await state.set_state(DuelAdd.nick)

@dp.message(DuelAdd.nick)
async def duel_nick(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    nick = msg.text.strip()
    if len(nick) < 3:
        await msg.answer("❌ Nik kamida 3 ta belgi bo'lsin, qaytadan kiriting:")
        return
    await state.update_data(d_nick=nick)
    await msg.answer(T(lang, "bio_prompt"), reply_markup=skip_cancel_kb(lang))
    await state.set_state(DuelAdd.bio)

@dp.message(DuelAdd.bio)
async def duel_bio(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    bio = "" if msg.text == T(lang, "skip") else msg.text.strip()
    d        = await state.get_data()
    uname    = msg.from_user.username or "user"
    photo_id = d.get("d_photo")
    nick     = d.get("d_nick", "")
    await state.clear()
    await add_duel(uid, uname, nick, bio, photo_id)
    await post_duel_to_channel(uname, nick, bio, photo_id)
    await msg.answer("✅ *Duel e'loningiz joylandi!*", reply_markup=main_kb(lang))

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
    await send_event_sticker(msg.chat.id, "sales")
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
    await send_event_sticker(msg.chat.id, "online")
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
# 🎮 ROBLOX SKRIPT
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_roblox_script") for l in LANGS)))
async def cmd_roblox_script(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid  = msg.from_user.id
    await send_event_sticker(msg.chat.id, "roblox_script")
    lang = await get_user_lang(uid)
    b = InlineKeyboardBuilder()
    b.button(text=T(lang, "btn_roblox_script_link"), url=ROBLOX_SCRIPT_CHANNEL)
    b.adjust(1)
    await msg.answer(T(lang, "roblox_script_msg"), reply_markup=b.as_markup())

# ═══════════════════════════════════════════════════════
# 🍈 BLOX FRUIT BO'LIMI (Stock + Xizmatlar)
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_bloxfruit") for l in LANGS)))
async def cmd_bloxfruit(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    await send_event_sticker(msg.chat.id, "bloxfruit")
    b = InlineKeyboardBuilder()
    b.button(text="🍈 Kanalga o'tish", url="https://t.me/veko_blox_fruit")
    b.adjust(1)
    await msg.answer(
        "🍈 *Blox Fruit bo'limi*\n\n"
        "Blox Fruit bilan bog'liq barcha narsalarni (stock, xizmatlar, yangiliklar) "
        "shu yerdan ko'rishingiz mumkin:\n@veko_blox_fruit",
        reply_markup=b.as_markup()
    )

@dp.callback_query(F.data == "bf_stock")
async def cb_bf_stock(cb: types.CallbackQuery):
    url = await get_bf_stock_channel()
    b = InlineKeyboardBuilder()
    b.button(text="📦 Stock kanaliga o'tish", url=url)
    b.adjust(1)
    await cb.message.answer(
        "📦 *Stock*\n\n"
        "Barcha mavjud narsalar shu kanalda tashlanadi 👇",
        reply_markup=b.as_markup()
    )
    await cb.answer()

@dp.callback_query(F.data == "bf_services")
async def cb_bf_services(cb: types.CallbackQuery):
    b = InlineKeyboardBuilder()
    for key, label in BF_SERVICES:
        b.button(text=label, callback_data=key)
    b.adjust(1)
    await cb.message.answer(
        "🛠 *Blox Fruit xizmatlari*\n\n"
        "🆙 1️⃣ Lvl ko'tarib berish\n"
        "💰 2️⃣ Pul ko'paytirib berish\n"
        "🛡 3️⃣ Raidlardan o'tib berish\n"
        "🍈 4️⃣ Fruit sotiladi\n"
        "📦 5️⃣ 1+ Storage\n\n"
        "✅ Boshqa hamma xizmatlarni ham olib beramiz — *akkingizga kirib o'tirmaymiz!*\n\n"
        "👇 Kerakli xizmatni tanlang:",
        reply_markup=b.as_markup()
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("bf_") & ~F.data.in_(["bf_stock", "bf_services"]))
async def cb_bf_service_pick(cb: types.CallbackQuery, state: FSMContext):
    key = cb.data
    if key not in BF_SERVICES_TEXT:
        await cb.answer()
        return
    await state.update_data(bf_service=key)
    b = InlineKeyboardBuilder()
    b.button(text="🛒 Buyurtma berish", callback_data="bf_order_start")
    b.adjust(1)
    await cb.message.answer(BF_SERVICES_TEXT[key], reply_markup=b.as_markup())
    await cb.answer()

@dp.callback_query(F.data == "bf_order_start")
async def cb_bf_order_start(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    lang = await get_user_lang(uid)
    await cb.message.answer("🎮 Roblox nikingizni va qo'shimcha izohingizni yozing (masalan: nick + xohlagan natija):", reply_markup=cancel_kb(lang))
    await state.set_state(BFOrder.nick)
    await cb.answer()

@dp.message(BFOrder.nick)
async def bf_order_nick(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    d = await state.get_data()
    key = d.get("bf_service")
    label = dict(BF_SERVICES).get(key, key)
    await state.clear()
    await msg.answer(
        f"✅ *Buyurtmangiz qabul qilindi!*\n\n"
        f"🛠 Xizmat: {label}\n"
        f"📝 Izoh: {esc_md(msg.text.strip())}\n\n"
        f"👨‍💻 Tez orada admin siz bilan bog'lanadi.",
        reply_markup=main_kb(lang)
    )
    await notify_role_admins(
        "bloxfruit",
        f"🍈 *Yangi Blox Fruit xizmat buyurtmasi*\n\n"
        f"🛠 Xizmat: {label}\n"
        f"👤 @{esc_md(msg.from_user.username or '-')} (`{uid}`)\n"
        f"📝 Izoh: {esc_md(msg.text.strip())}\n"
        f"🕐 {now()}"
    )

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
    await msg.answer("🛡 *Trade qilib berish xizmati*\n\n👤 Admin: @notalonet", reply_markup=b.as_markup())

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
# GLOBAL MUTE MIDDLEWARE — /start va barcha tugma/komandalarni qamrab oladi
# ═══════════════════════════════════════════════════════
from aiogram import BaseMiddleware

class MuteMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and not is_admin(user.id):
            try:
                muted = await is_muted(user.id)
            except Exception:
                muted = False
            if muted:
                lang = await get_user_lang(user.id)
                rem = await mute_remaining(user.id)
                text = T(lang, "muted_msg", rem=rem)
                if isinstance(event, types.CallbackQuery):
                    try:
                        await event.answer(text.replace("*", ""), show_alert=True)
                    except Exception:
                        pass
                elif isinstance(event, types.Message):
                    try:
                        await event.answer(text)
                    except Exception:
                        pass
                return  # handlerga o'tkazmaymiz — bot ishlamaydi
        return await handler(event, data)

dp.message.outer_middleware(MuteMiddleware())
dp.callback_query.outer_middleware(MuteMiddleware())

# ═══════════════════════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════════════════════
async def admin_panel_kb():
    tr  = await active_trades()
    sl  = await active_sales()
    or_ = await pending_orders()
    cnt = await users_count()
    b   = InlineKeyboardBuilder()
    b.button(text=f"📦 Buyurtmalar ({len(or_)})", callback_data="adm_ord")
    b.button(text=f"🔄 Tradelar ({len(tr)})",     callback_data="adm_tr")
    b.button(text=f"🛍 Sotuvlar ({len(sl)})",      callback_data="adm_sl")
    b.button(text="📢 Broadcast",                  callback_data="adm_bc")
    b.button(text="➕ Balans qo'shish",            callback_data="adm_addbal")
    b.button(text="➖ Balans ayirish",             callback_data="adm_subbal")
    b.button(text="🔇 Mute berish",                callback_data="adm_mute")
    b.button(text="👥 Foydalanuvchilar",           callback_data="adm_users_0")
    b.button(text="👑 Admin qo'shish",             callback_data="adm_addadmin")
    b.button(text="💱 Valyuta kurslari",           callback_data="adm_rates")
    b.button(text="🎭 Stikerlar boshqaruvi",       callback_data="adm_sticker_menu")
    b.button(text="📦 Stock kanal havolasi",       callback_data="adm_stock_url")
    b.button(text="💎 Pro ilova yuklash",          callback_data="adm_pro_upload")
    b.button(text="🎟 Promokodlar",                callback_data="adm_promo_menu")
    b.button(text="🪙 Robux kursi",                callback_data="adm_robux_rate")
    b.adjust(2, 2, 2, 2, 2, 1, 1, 1, 2)
    return b.as_markup(), cnt, or_, tr, sl

@dp.message(Command("admin"))
async def cmd_admin(msg: types.Message):
    uid = msg.from_user.id
    if is_admin(uid):
        markup, cnt, or_, tr, sl = await admin_panel_kb()
        await msg.answer(
            f"🛠 *Admin Panel*\n\n👥 Foydalanuvchilar: *{cnt}*\n"
            f"📦 Kutayotgan buyurtmalar: *{len(or_)}*\n"
            f"🔄 Faol tradelar: *{len(tr)}*\n🛍 Faol sotuvlar: *{len(sl)}*",
            reply_markup=markup
        )
        return

    role = get_admin_role(uid)
    if role is None:
        await msg.answer("❌ Ruxsat yo'q!")
        return

    b = InlineKeyboardBuilder()
    if role == "referral":
        or_ps = await private_orders_db.count_documents({"status": "pending"})
        b.button(text=f"🎁 Referal so'rovlari ({or_ps})", callback_data="adm_psorders")
        b.adjust(1)
        await msg.answer(
            f"🎁 *Referal Admin Panel*\n\n"
            f"Bu yerda faqat referal orqali olinadigan Privat Server so'rovlarini "
            f"tasdiqlashingiz yoki rad etishingiz mumkin.",
            reply_markup=b.as_markup()
        )
    elif role == "robux":
        ol = await pending_orders()
        b.button(text=f"📦 Robux buyurtmalar ({len(ol)})", callback_data="adm_ord")
        b.adjust(1)
        await msg.answer(
            f"🪙 *Robux Admin Panel*\n\n"
            f"Bu yerda faqat Robux sotib olish buyurtmalarini "
            f"tasdiqlashingiz yoki rad etishingiz mumkin.",
            reply_markup=b.as_markup()
        )

@dp.callback_query(F.data == "adm_ord")
async def adm_ord(cb: types.CallbackQuery):
    if not is_robux_admin(cb.from_user.id):
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

@dp.callback_query(F.data == "adm_psorders")
async def adm_psorders(cb: types.CallbackQuery):
    if not is_referral_admin(cb.from_user.id):
        return
    ol = [o async for o in private_orders_db.find({"status": "pending"}).sort("_id", -1).limit(10)]
    if not ol:
        await cb.answer("Kutayotgan referal so'rovlari yo'q!", show_alert=True)
        return
    for o in ol:
        info = PRIVATE_GAME_LABELS.get(o.get("game", ""), ("O'yin", 0))
        nicks = o.get("submitted_nicks") or []
        b = InlineKeyboardBuilder()
        b.button(text="✅ Tasdiqlash", callback_data=f"ps_ok_{o['_id']}")
        b.button(text="❌ Rad etish",  callback_data=f"ps_no_{o['_id']}")
        b.adjust(2)
        await cb.message.answer(
            f"🎮 *Referal so'rovi #{short_id(o['_id'])}*\n👤 @{esc_md(o.get('username','-'))}\n"
            f"🎮 O'yin: *{info[0]}*\n🔑 Nik: `{esc_md(o.get('roblox_nick',''))}`\n"
            f"👥 Kishilar: *{o.get('player_count','-')}*\n"
            + ("📝 Niklar:\n" + "\n".join(f"• `{esc_md(n)}`" for n in nicks) if nicks else ""),
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

@dp.callback_query(F.data == "adm_rates")
async def adm_rates(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    rates = await get_currency_rates()
    await cb.message.answer(
        f"💱 *Valyuta kurslari* (bazaviy: so'm)\n\n"
        f"🇺🇸 1 USD = *{rates.get('USD', 0):,.0f}* so'm\n"
        f"🇷🇺 1 RUB = *{rates.get('RUB', 0):,.0f}* so'm\n\n"
        f"Bu kurslar tilni o'zgartirganda barcha narxlarni (Robux, hisob to'ldirish va h.k.) "
        f"tegishli valyutaga avtomatik qayta hisoblash uchun ishlatiladi.\n\n"
        f"Yangi USD kursini kiriting (1 USD necha so'm):",
        reply_markup=cancel_kb()
    )
    await state.set_state(RateEdit.usd)
    await cb.answer()

@dp.message(RateEdit.usd)
async def rate_set_usd(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    txt = msg.text.strip().replace(" ", "").replace(",", "")
    try:
        val = float(txt)
        if val <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ Musbat raqam kiriting (masalan: 12700):")
        return
    await state.update_data(new_usd=val)
    await msg.answer("Endi yangi RUB kursini kiriting (1 RUB necha so'm):", reply_markup=cancel_kb())
    await state.set_state(RateEdit.rub)

@dp.message(RateEdit.rub)
async def rate_set_rub(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    txt = msg.text.strip().replace(" ", "").replace(",", "")
    try:
        val = float(txt)
        if val <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ Musbat raqam kiriting (masalan: 155):")
        return
    d = await state.get_data()
    usd_val = d.get("new_usd")
    await set_currency_rate("USD", usd_val)
    await set_currency_rate("RUB", val)
    await state.clear()
    await msg.answer(
        f"✅ Kurslar yangilandi!\n\n🇺🇸 1 USD = {usd_val:,.0f} so'm\n🇷🇺 1 RUB = {val:,.0f} so'm",
        reply_markup=main_kb(lang)
    )

# ═══════════════════════════════════════════════════════
# ADMIN — ROBUX AYIRBOSHLASH KURSI
# ═══════════════════════════════════════════════════════
@dp.callback_query(F.data == "adm_robux_rate")
async def adm_robux_rate(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    rate = await get_robux_rate()
    rate_per_1000 = rate * 1000
    await cb.message.answer(
        f"🪙 *Robux ayirboshlash kursi*\n\n"
        f"Hozirgi kurs: har *1000 so'm* uchun *{fmt_robux(rate_per_1000)} Robux*.\n\n"
        f"Bu kurs quyidagilarga qo'llaniladi:\n"
        f"• Hisob to'ldirish tasdiqlanganda avtomatik Robux bonus\n"
        f"• Saytdagi balansni Robux'ga almashtirish tugmasi\n\n"
        f"Yangi kursni kiriting (1000 so'mga necha Robux to'g'ri kelishini, masalan: `0.01`):",
        reply_markup=cancel_kb()
    )
    await state.set_state(RobuxRateEdit.rate)
    await cb.answer()

@dp.message(RobuxRateEdit.rate)
async def robux_rate_set(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    txt = msg.text.strip().replace(",", ".")
    try:
        val = float(txt)
        if val < 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ Musbat raqam kiriting (masalan: 0.01):")
        return
    await set_robux_rate(val)
    await state.clear()
    await msg.answer(f"✅ Yangi kurs saqlandi!\n\n🪙 Har *1000 so'm* uchun *{fmt_robux(val)} Robux*.", reply_markup=main_kb(lang))

# ═══════════════════════════════════════════════════════
# ADMIN — PROMOKODLAR BOSHQARUVI
# ═══════════════════════════════════════════════════════
def _promo_menu_kb():
    b = InlineKeyboardBuilder()
    b.button(text="➕ Yangi promokod",      callback_data="adm_promo_add")
    b.button(text="📋 Promokodlar ro'yxati", callback_data="adm_promo_list")
    b.button(text="🗑 Promokodni o'chirish", callback_data="adm_promo_del")
    b.button(text="🔙 Admin panel",         callback_data="adm_back")
    b.adjust(1, 1, 1, 1)
    return b.as_markup()

@dp.callback_query(F.data == "adm_promo_menu")
async def adm_promo_menu(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    total = await promocodes_col.count_documents({})
    await cb.message.answer(f"🎟 *Promokodlar boshqaruvi*\n\nJami promokodlar: *{total}* ta", reply_markup=_promo_menu_kb())
    await cb.answer()

@dp.callback_query(F.data == "adm_promo_add")
async def adm_promo_add(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await cb.message.answer(
        "🎟 *Yangi promokod*\n\nPromokod nomini kiriting (masalan: `VEKO2026`):",
        reply_markup=cancel_kb()
    )
    await state.set_state(PromoCreate.code)
    await cb.answer()

@dp.message(PromoCreate.code)
async def promo_create_code(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    code = (msg.text or "").strip().upper()
    if not code or " " in code:
        await msg.answer("❌ Promokod bo'sh yoki probelsiz bo'lishi kerak. Qaytadan kiriting:")
        return
    existing = await get_promo(code)
    if existing:
        await msg.answer("❌ Bu nomdagi promokod allaqachon mavjud. Boshqa nom kiriting:")
        return
    await state.update_data(promo_code=code)
    b = InlineKeyboardBuilder()
    b.button(text="💵 So'm (balans)", callback_data="promo_cur_uzs")
    b.button(text="🪙 Robux",         callback_data="promo_cur_robux")
    b.adjust(2)
    await msg.answer(f"✅ Kod: `{code}`\n\n💱 Promokod qaysi valyutada bo'lsin?", reply_markup=b.as_markup())
    await state.set_state(PromoCreate.currency)

@dp.callback_query(PromoCreate.currency, F.data.startswith("promo_cur_"))
async def promo_create_currency(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    currency = cb.data.split("promo_cur_")[1]  # "uzs" | "robux"
    await state.update_data(promo_currency=currency)
    label = "so'm" if currency == "uzs" else "Robux"
    await cb.message.answer(f"💰 Har bir foydalanuvchiga necha *{label}* berilsin? Miqdorni kiriting:", reply_markup=cancel_kb())
    await state.set_state(PromoCreate.amount)
    await cb.answer()

@dp.message(PromoCreate.amount)
async def promo_create_amount(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    txt = msg.text.strip().replace(" ", "").replace(",", ".")
    try:
        amount = float(txt)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ Musbat raqam kiriting:")
        return
    d = await state.get_data()
    if d.get("promo_currency") == "uzs":
        amount = int(amount)
    await state.update_data(promo_amount=amount)
    await msg.answer("👥 Promokodni nechta odam ishlata olsin? (masalan: `100`):", reply_markup=cancel_kb())
    await state.set_state(PromoCreate.max_uses)

@dp.message(PromoCreate.max_uses)
async def promo_create_max_uses(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    txt = msg.text.strip()
    if not txt.isdigit() or int(txt) <= 0:
        await msg.answer("❌ Musbat butun son kiriting (masalan: 100):")
        return
    max_uses = int(txt)
    d = await state.get_data()
    code     = d["promo_code"]
    currency = d["promo_currency"]
    amount   = d["promo_amount"]
    await create_promo(code, currency, amount, max_uses, uid)
    await state.clear()
    label = "so'm" if currency == "uzs" else "Robux"
    amt_str = f"{amount:,}" if currency == "uzs" else fmt_robux(amount)
    await msg.answer(
        f"✅ *Promokod yaratildi!*\n\n"
        f"🎟 Kod: `{code}`\n"
        f"💰 Miqdor: *{amt_str} {label}*\n"
        f"👥 Limit: *{max_uses}* ta foydalanuvchi\n\n"
        f"Foydalanuvchilar 🎟 *Promokod* tugmasi orqali kodni kiritishi mumkin.",
        reply_markup=main_kb(lang)
    )

@dp.callback_query(F.data == "adm_promo_list")
async def adm_promo_list(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    promos = await list_promos()
    if not promos:
        await cb.message.answer("📭 Hozircha promokodlar yo'q.")
        await cb.answer()
        return
    lines = ["📋 *Promokodlar ro'yxati:*\n"]
    for p in promos[:50]:
        label = "so'm" if p.get("currency") == "uzs" else "Robux"
        amt_str = f"{p.get('amount', 0):,}" if p.get("currency") == "uzs" else fmt_robux(p.get("amount", 0))
        status = "✅ Faol" if p.get("active", True) else "⛔ O'chirilgan"
        lines.append(
            f"🎟 `{p['code']}` — {amt_str} {label}\n"
            f"👥 {p.get('used_count', 0)}/{p.get('max_uses', 0)} ishlatilgan • {status}"
        )
    await cb.message.answer("\n\n".join(lines))
    await cb.answer()

@dp.callback_query(F.data == "adm_promo_del")
async def adm_promo_del(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await cb.message.answer("🗑 O'chirmoqchi bo'lgan promokod nomini kiriting:", reply_markup=cancel_kb())
    await state.set_state(PromoDelete.code)
    await cb.answer()

@dp.message(PromoDelete.code)
async def promo_delete_handler(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    code = (msg.text or "").strip().upper()
    ok = await delete_promo(code)
    await state.clear()
    if ok:
        await msg.answer(f"✅ `{code}` promokodi o'chirildi.", reply_markup=main_kb(lang))
    else:
        await msg.answer(f"❌ `{code}` nomli promokod topilmadi.", reply_markup=main_kb(lang))

@dp.callback_query(F.data == "adm_sticker_menu")
async def adm_sticker_menu(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    b = InlineKeyboardBuilder()
    for key, label in STICKER_SECTIONS:
        current = await get_sticker(key)
        mark = "✅" if current else "➖"
        b.button(text=f"{mark} {label}", callback_data=f"adm_sticker_pick_{key}")
    b.button(text="🔙 Admin panel", callback_data="adm_back")
    b.adjust(1)
    await cb.message.answer(
        "🎭 *Stikerlar boshqaruvi*\n\n"
        "Har bir bo'lim uchun alohida stiker o'rnatishingiz mumkin — foydalanuvchi "
        "shu bo'limni ochganda stiker avtomatik yuboriladi.\n\n"
        "✅ — stiker o'rnatilgan   ➖ — stiker yo'q\n\n"
        "Bo'limni tanlang:",
        reply_markup=b.as_markup()
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("adm_sticker_pick_"))
async def adm_sticker_pick(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    event_key = cb.data[len("adm_sticker_pick_"):]
    label = dict(STICKER_SECTIONS).get(event_key, event_key)
    current = await get_sticker(event_key)
    await state.update_data(sticker_event=event_key)
    b = InlineKeyboardBuilder()
    if current:
        b.button(text="🗑 Stikerni o'chirish", callback_data=f"adm_sticker_del_{event_key}")
        b.adjust(1)
    if current:
        await cb.message.answer_sticker(current)
    await cb.message.answer(
        f"🎭 *{esc_md(label)}* uchun stiker o'rnatish\n\n"
        f"Botga yangi stiker yuboring — u endi shu bo'lim ochilganda yuboriladi.",
        reply_markup=b.as_markup() if current else cancel_kb()
    )
    await state.set_state(StickerSet.waiting)
    await cb.answer()

@dp.callback_query(F.data.startswith("adm_sticker_del_"))
async def adm_sticker_del(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    event_key = cb.data[len("adm_sticker_del_"):]
    await remove_sticker(event_key)
    await cb.answer("✅ Stiker o'chirildi!", show_alert=True)
    await adm_sticker_menu(cb)

@dp.message(StickerSet.waiting, F.sticker)
async def sticker_set_receive(msg: types.Message, state: FSMContext):
    lang = await get_user_lang(msg.from_user.id)
    d = await state.get_data()
    event_key = d.get("sticker_event", "start")
    label = dict(STICKER_SECTIONS).get(event_key, event_key)
    await set_sticker(event_key, msg.sticker.file_id)
    await state.clear()
    await msg.answer(f"✅ *{esc_md(label)}* uchun stiker o'rnatildi!", reply_markup=main_kb(lang))

@dp.message(StickerSet.waiting)
async def sticker_set_wrong(msg: types.Message, state: FSMContext):
    lang = await get_user_lang(msg.from_user.id)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await msg.answer("❗️ Iltimos, aynan *stiker* yuboring (matn emas).")

@dp.callback_query(F.data == "adm_stock_url")
async def adm_stock_url(cb: types.CallbackQuery, state: FSMContext):
    if not (is_admin(cb.from_user.id) or is_stock_admin(cb.from_user.id)):
        return
    cur = await get_bf_stock_channel()
    await cb.message.answer(
        f"📦 *Stock kanal havolasi*\n\nHozirgi: {cur}\n\nYangi havolani yuboring (masalan: `https://t.me/kanalim`):",
        reply_markup=cancel_kb()
    )
    await state.set_state(StockEdit.url)
    await cb.answer()

@dp.message(StockEdit.url)
async def stock_url_receive(msg: types.Message, state: FSMContext):
    lang = await get_user_lang(msg.from_user.id)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    url = msg.text.strip()
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("@")):
        await msg.answer("❌ To'g'ri havola yuboring (https:// bilan boshlanishi kerak):")
        return
    await set_bf_stock_channel(url)
    await state.clear()
    await msg.answer(f"✅ Stock kanal havolasi yangilandi:\n{url}", reply_markup=main_kb(lang))

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
# 👑 ADMIN QO'SHISH (faqat Super admin)
# ═══════════════════════════════════════════════════════
@dp.callback_query(F.data == "adm_addadmin")
async def adm_addadmin(cb: types.CallbackQuery):
    if not is_super_admin(cb.from_user.id):
        return
    b = InlineKeyboardBuilder()
    b.button(text="👑 Super admin",        callback_data="addrole_super")
    b.button(text="🎁 Referal admin",      callback_data="addrole_referral")
    b.button(text="🪙 Robux admin",        callback_data="addrole_robux")
    b.button(text="📦 Stock admin",        callback_data="addrole_stock")
    b.button(text="🍈 Xizmatlar admin",    callback_data="addrole_bloxfruit")
    b.button(text="📋 Adminlar ro'yxati",  callback_data="adm_listadmins")
    b.button(text="🔙 Admin panel",        callback_data="adm_back")
    b.adjust(1)
    await cb.message.answer(
        "👑 *Admin qo'shish*\n\n"
        "Quyidagi bo'limlardan birini tanlang:\n\n"
        "👑 *Super admin* — hamma narsaga to'liq ruxsat\n"
        "🎁 *Referal admin* — faqat referal/privat server so'rovlarini tasdiqlaydi\n"
        "🪙 *Robux admin* — faqat Robux buyurtmalarini tasdiqlaydi\n"
        "📦 *Stock admin* — Blox Fruit Stock kanal havolasini boshqaradi\n"
        "🍈 *Xizmatlar admin* — Blox Fruit xizmatlar buyurtmalarini qabul qiladi/tahrirlaydi\n\n"
        "Rolni tanlang, so'ng foydalanuvchi ID raqamini yuborasiz:",
        reply_markup=b.as_markup()
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("addrole_"))
async def adm_addrole_pick(cb: types.CallbackQuery, state: FSMContext):
    if not is_super_admin(cb.from_user.id):
        return
    role = cb.data[len("addrole_"):]
    if role not in ADMIN_ROLE_LABELS:
        await cb.answer()
        return
    await state.update_data(new_admin_role=role)
    await cb.message.answer(
        f"🆔 {ADMIN_ROLE_LABELS[role]} sifatida qo'shmoqchi bo'lgan foydalanuvchining "
        f"Telegram ID raqamini yuboring:",
        reply_markup=cancel_kb()
    )
    await state.set_state(AdminRoleAdd.user_id)
    await cb.answer()

@dp.message(AdminRoleAdd.user_id)
async def adm_addrole_uid(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel") or msg.text in ("❌ Bekor qilish", "❌ Cancel", "❌ Отмена"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    txt = msg.text.strip()
    if not txt.isdigit():
        await msg.answer("❌ Faqat ID raqam yuboring (masalan: 123456789):")
        return
    target_id = int(txt)
    d = await state.get_data()
    role = d.get("new_admin_role")
    if role not in ADMIN_ROLE_LABELS:
        await state.clear()
        await msg.answer("❌ Xatolik! Qaytadan boshlang.", reply_markup=main_kb(lang))
        return
    await add_admin_role(target_id, role)
    await state.clear()
    await msg.answer(
        f"✅ Foydalanuvchi `{target_id}` endi *{ADMIN_ROLE_LABELS[role]}* etib tayinlandi!",
        reply_markup=main_kb(lang)
    )
    try:
        await bot.send_message(
            target_id,
            f"🎉 Tabriklaymiz! Siz botda *{ADMIN_ROLE_LABELS[role]}* etib tayinlandingiz.\n"
            f"Boshqaruv paneliga kirish uchun /admin buyrug'ini yuboring."
        )
    except Exception:
        pass

@dp.callback_query(F.data == "adm_listadmins")
async def adm_listadmins(cb: types.CallbackQuery):
    if not is_super_admin(cb.from_user.id):
        return
    await _render_admins_list(cb.message)
    await cb.answer()

async def _render_admins_list(message: types.Message):
    """Qara adminlar bo'limi: barcha tayinlangan adminlar ro'yxati,
    har biri uchun O'chirish tugmasi va pastda Ortga tugmasi."""
    lines = ["👑 *Qara adminlar ro'yxati*\n"]
    for aid in sorted(ADMIN_IDS):
        lines.append(f"👑 `{aid}` — Super admin (asosiy, o'chirib bo'lmaydi)")
    if not ADMIN_ROLES:
        lines.append("\n_Hozircha tayinlangan adminlar yo'q._")
    else:
        for aid, role in ADMIN_ROLES.items():
            lines.append(f"{ADMIN_ROLE_LABELS.get(role,'❓')} `{aid}` — {ADMIN_ROLE_LABELS.get(role, role)}")

    b = InlineKeyboardBuilder()
    for aid, role in ADMIN_ROLES.items():
        b.button(
            text=f"🗑 O'chirish: {aid} ({ADMIN_ROLE_LABELS.get(role, role)})",
            callback_data=f"deladmin_{aid}"
        )
    b.button(text="⬅️ Ortga", callback_data="adm_back")
    b.adjust(1)

    try:
        await message.edit_text("\n".join(lines), reply_markup=b.as_markup())
    except Exception:
        await message.answer("\n".join(lines), reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("deladmin_"))
async def adm_deladmin(cb: types.CallbackQuery):
    if not is_super_admin(cb.from_user.id):
        return
    target_id = int(cb.data[len("deladmin_"):])
    if target_id in ADMIN_IDS:
        await cb.answer("❌ Asosiy super adminni o'chirib bo'lmaydi!", show_alert=True)
        return
    if target_id not in ADMIN_ROLES:
        await cb.answer("Bu admin allaqachon o'chirilgan!", show_alert=True)
        await _render_admins_list(cb.message)
        return
    old_role = ADMIN_ROLES.get(target_id)
    await remove_admin_role(target_id)
    try:
        await bot.send_message(
            target_id,
            f"❌ Siz *{ADMIN_ROLE_LABELS.get(old_role, old_role)}* lavozimidan olib tashlandingiz."
        )
    except Exception:
        pass
    await cb.answer("✅ Admin olib tashlandi!", show_alert=True)
    await _render_admins_list(cb.message)

# ═══════════════════════════════════════════════════════
# 🏆 YUTUQLI O'YIN (Web App) — WEBAPP_URL sozlanmagan holat uchun fallback
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: (not WEBAPP_URL) and any(msg.text == T(l, "btn_game") for l in LANGS)))
async def cmd_game_not_configured(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    await msg.answer("⚙️ Web App manzili hali sozlanmagan. Iltimos, admin bilan bog'laning.")

@dp.message(F.func(lambda msg: bool(WEBAPP_URL) and any(msg.text == T(l, "btn_game") for l in LANGS)))
async def cmd_game_open_prompt(msg: types.Message, state: FSMContext):
    """'Yutuqli o'yin' tugmasi bosilganda o'yinni to'g'ridan-to'g'ri ochmaydi,
    balki 'Kirish uchun bosing' degan inline tugma bilan xabar yuboradi.
    (Inline web_app tugmasi barcha Telegram klientlarida initData'ni ishonchli uzatadi.)"""
    if not await check_access(msg, state):
        return
    lang = await get_user_lang(msg.from_user.id)
    kb = InlineKeyboardBuilder()
    kb.button(text="🚀 Kirish uchun bosing", web_app=WebAppInfo(url=WEBAPP_URL))
    await msg.answer("🏆 O'yinga kirish uchun quyidagi tugmani bosing:", reply_markup=kb.as_markup())

# ═══════════════════════════════════════════════════════
# 🎁 REFERAL BO'LIMI
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_referral") for l in LANGS)))
async def cmd_referral(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid   = msg.from_user.id
    await send_event_sticker(msg.chat.id, "referral")
    lang  = await get_user_lang(uid)
    uname = msg.from_user.username or ""
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref{uid}"
    ref_count = await get_ref_count(uid)

    text = (
        f"🎁 **Referal tizimi**\n\n"
        f"🔗 Havolangizni do'stlaringizga yuboring!\n"
        f"Har bir yangi foydalanuvchi uchun **1 referal** qo'shiladi.\n\n"
        f"👥 Sizning referallaringiz: **{ref_count} ta**\n\n"
        f"🆓 **Tekinga Privat Server olish:**\n"
        f"Referallaringiz orqali privat server yutib oling!\n\n"
        f"📋 Havolangiz:\n`{ref_link}`"
    )
    b = InlineKeyboardBuilder()
    b.button(text="📋 Havolani nusxalash", copy_text=types.CopyTextButton(text=ref_link))
    b.button(text="🎮 Referallarni ishlatish", callback_data="ref_use")
    b.button(text="🏆 Top 20 Reyting", callback_data="ref_top")
    b.adjust(1)
    await msg.answer(text, reply_markup=b.as_markup())

@dp.callback_query(F.data == "ref_use")
async def cb_ref_use(cb: types.CallbackQuery):
    uid       = cb.from_user.id
    ref_count = await get_ref_count(uid)

    text = (
        f"🎁 **Referallaringiz:** {ref_count} ta\n\n"
        f"🔄 **SHOP — Privat server narxlari:**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"1️⃣ 🧠 **Steal a Brainrot** ➡️ 5 ta referal\n"
        f"2️⃣ 🍎 **Blox Fruit** ➡️ 6 ta referal\n"
        f"3️⃣ 🔪 **MM2** ➡️ 4 ta referal\n"
        f"4️⃣ 🌊 **Escape Tsunami** ➡️ 3 ta referal\n"
        f"5️⃣ 🎲 **Mystery Die** ➡️ 3 ta referal\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    b = InlineKeyboardBuilder()
    b.button(text="🎮 Privat Server olish", callback_data="private_server_start")
    b.adjust(1)
    await cb.message.edit_text(text, reply_markup=b.as_markup())
    await cb.answer()

@dp.callback_query(F.data == "ref_top")
async def cb_ref_top(cb: types.CallbackQuery):
    top = await get_top_referrals(20)
    if not top:
        await cb.answer("Hozircha reyting bo'sh!", show_alert=True)
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 **TOP 20 — Referal Reytingi**\n━━━━━━━━━━━━━━━━━━━━"]
    for i, u in enumerate(top, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        uname = u.get("username") or "-"
        cnt   = u.get("ref_count", 0)
        lines.append(f"{medal} @{uname} — **{cnt}** referal")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    await cb.message.edit_text("\n".join(lines))
    await cb.answer()

@dp.callback_query(F.data == "my_refs")
async def cb_my_refs(cb: types.CallbackQuery):
    uid       = cb.from_user.id
    ref_count = await get_ref_count(uid)
    ref_link  = f"https://t.me/{(await bot.get_me()).username}?start=ref{uid}"

    text = (
        f"🎁 **Referallaringiz:** {ref_count} ta\n\n"
        f"🔗 Havolangiz:\n`{ref_link}`\n\n"
        f"🔄 **SHOP — Privat server narxlari:**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"1️⃣ 🧠 **Steal a Brainrot** ➡️ 5 ta referal\n"
        f"2️⃣ 🍎 **Blox Fruit** ➡️ 6 ta referal\n"
        f"3️⃣ 🔪 **MM2** ➡️ 4 ta referal\n"
        f"4️⃣ 🌊 **Escape Tsunami** ➡️ 3 ta referal\n"
        f"5️⃣ 🎲 **Mystery Die** ➡️ 3 ta referal\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    b = InlineKeyboardBuilder()
    b.button(text="📋 Havolani nusxalash", copy_text=types.CopyTextButton(text=ref_link))
    b.button(text="🎮 Privat Server olish", callback_data="private_server_start")
    b.button(text="🏆 Top 20 Reyting", callback_data="ref_top")
    b.adjust(1)
    await cb.message.answer(text, reply_markup=b.as_markup())
    await cb.answer()

# ═══════════════════════════════════════════════════════
# 🎮 PRIVAT SERVER BO'LIMI
# ═══════════════════════════════════════════════════════
@dp.callback_query(F.data == "private_server_start")
async def cb_private_server_start(cb: types.CallbackQuery, state: FSMContext):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    b = InlineKeyboardBuilder()
    for key, label, cost in PRIVATE_GAMES:
        ref_count = await get_ref_count(uid)
        status = "✅" if ref_count >= cost else "🔒"
        b.button(text=f"{status} {label} — {cost} referal", callback_data=f"ps_game_{key}")
    b.button(text="❌ Bekor qilish", callback_data="ps_cancel")
    b.adjust(1)
    ref_count = await get_ref_count(uid)
    await cb.message.answer(
        f"🎮 **Privat Server olish**\n\n"
        f"👥 Sizning referallaringiz: **{ref_count} ta**\n\n"
        f"Qaysi o'yin uchun privat server kerak?",
        reply_markup=b.as_markup()
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("ps_game_"))
async def cb_ps_game(cb: types.CallbackQuery, state: FSMContext):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    game = cb.data[len("ps_game_"):]
    info = PRIVATE_GAME_LABELS.get(game)
    if not info:
        await cb.answer("❌ Noto'g'ri o'yin!", show_alert=True)
        return
    label, cost = info
    ref_count = await get_ref_count(uid)
    if ref_count < cost:
        await cb.answer(
            f"❌ Yetarli referal yo'q!\nKerak: {cost} ta\nSizda: {ref_count} ta",
            show_alert=True
        )
        return
    await state.update_data(ps_game=game, ps_cost=cost, ps_label=label)
    await cb.message.answer(
        f"🎮 **{label}** uchun privat server\n\n"
        f"💸 Narxi: **{cost} ta referal**\n\n"
        f"📝 Roblox nikinigizni kiriting:",
        reply_markup=cancel_kb(lang)
    )
    await state.set_state(PrivateServerFlow.roblox_nick)
    await cb.answer()

@dp.message(PrivateServerFlow.roblox_nick)
async def ps_roblox_nick(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    nick = msg.text.strip()
    if len(nick) < 3:
        await msg.answer("❌ Nik kamida 3 ta belgi bo'lsin:")
        return
    await state.update_data(ps_roblox_nick=nick)
    await msg.answer(
        f"🎮 Roblox nik: `{esc_md(nick)}`\n\n"
        f"👥 Necha kishilik privat server kerak?",
        reply_markup=cancel_kb(lang)
    )
    await state.set_state(PrivateServerFlow.player_count)

@dp.message(PrivateServerFlow.player_count)
async def ps_player_count(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    txt = msg.text.strip()
    if not txt.isdigit() or int(txt) < 1 or int(txt) > 100:
        await msg.answer("❌ 1 dan 100 gacha raqam kiriting:")
        return
    await state.update_data(ps_player_count=int(txt))
    d = await state.get_data()
    await msg.answer(
        f"📋 **Buyurtma ma'lumotlari:**\n\n"
        f"🎮 O'yin: **{d['ps_label']}**\n"
        f"👤 Roblox nik: `{esc_md(d['ps_roblox_nick'])}`\n"
        f"👥 Kishilar soni: **{d['ps_player_count']}**\n\n"
        f"➕ Privatga qo'shmoqchi bo'lgan barcha akkountlaringizning Roblox niklarini yuboring:\n"
        f"_(Har bir nikni yangi qatorga yozing)_",
        reply_markup=cancel_kb(lang)
    )
    await state.set_state(PrivateServerFlow.submit_nicks)

@dp.message(PrivateServerFlow.submit_nicks)
async def ps_submit_nicks(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    nicks = [n.strip() for n in msg.text.strip().split("\n") if n.strip()]
    d = await state.get_data()

    b = InlineKeyboardBuilder()
    b.button(text="✅ Tashladik", callback_data="ps_confirm")
    b.button(text="❌ Bekor qilish", callback_data="ps_cancel_flow")
    b.adjust(1)
    await state.update_data(ps_nicks=nicks)
    await msg.answer(
        f"📋 **Tekshiring:**\n\n"
        f"🎮 O'yin: **{d['ps_label']}**\n"
        f"👤 Asosiy nik: `{esc_md(d['ps_roblox_nick'])}`\n"
        f"👥 Soni: **{d['ps_player_count']}** kishi\n"
        f"📝 Niklar:\n" + "\n".join(f"• `{esc_md(n)}`" for n in nicks),
        reply_markup=b.as_markup()
    )

@dp.callback_query(F.data == "ps_confirm")
async def ps_confirm(cb: types.CallbackQuery, state: FSMContext):
    uid   = cb.from_user.id
    lang  = await get_user_lang(uid)
    d     = await state.get_data()
    game  = d.get("ps_game")
    cost  = d.get("ps_cost", 0)
    label = d.get("ps_label", "")
    nick  = d.get("ps_roblox_nick", "")
    count = d.get("ps_player_count", 0)
    nicks = d.get("ps_nicks", [])
    uname = cb.from_user.username or "-"

    # Referalni yana tekshir (bir vaqtda ikki marta bosmasligi uchun)
    ref_count = await get_ref_count(uid)
    if ref_count < cost:
        await cb.answer(f"❌ Yetarli referal yo'q! Kerak: {cost}", show_alert=True)
        await state.clear()
        return

    # Referallarni yechi
    await users.update_one({"user_id": uid}, {"$inc": {"ref_count": -cost}})

    oid = await add_private_order(uid, uname, game, nick, count, cost)

    # Adminga xabar
    admin_text = (
        f"🎮 **Yangi Privat Server so'rovi** #{short_id(oid)}\n\n"
        f"👤 @{esc_md(uname)} (`{uid}`)\n"
        f"🎮 O'yin: **{label}**\n"
        f"🔑 Asosiy nik: `{esc_md(nick)}`\n"
        f"👥 Kishilar: **{count}**\n"
        f"📝 Niklar:\n" + "\n".join(f"• `{esc_md(n)}`" for n in nicks) +
        f"\n\n💸 Yechildi: **{cost} ta referal**"
    )
    ab = InlineKeyboardBuilder()
    ab.button(text="✅ Tasdiqlash", callback_data=f"ps_ok_{oid}")
    ab.button(text="❌ Rad etish",  callback_data=f"ps_no_{oid}")
    ab.adjust(2)
    await notify_role_admins("referral", admin_text, markup=ab.as_markup())
    await state.clear()

    await cb.message.answer(
        f"✅ **So'rovingiz qabul qilindi!**\n\n"
        f"⏰ 5 soat ichida privat serveringiz ochiladi.\n"
        f"Admin tasdiqlashini kuting.",
        reply_markup=main_kb(lang)
    )
    await cb.answer()

@dp.callback_query(F.data == "ps_cancel_flow")
async def ps_cancel_flow(cb: types.CallbackQuery, state: FSMContext):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    await state.clear()
    await cb.message.edit_text("❌ Bekor qilindi.")
    await cb.message.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
    await cb.answer()

@dp.callback_query(F.data == "ps_cancel")
async def ps_cancel(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    lang = await get_user_lang(uid)
    await cb.message.edit_text("❌ Bekor qilindi.")
    await cb.answer()

@dp.callback_query(F.data.startswith("ps_ok_"))
async def ps_admin_ok(cb: types.CallbackQuery):
    if not is_referral_admin(cb.from_user.id):
        return
    oid = cb.data[len("ps_ok_"):]
    o   = await get_private_order(oid)
    if not o or o["status"] != "pending":
        await cb.answer("Allaqachon ko'rilgan!", show_alert=True)
        return
    await approve_private_order(oid)
    user_lang = await get_user_lang(o["user_id"])
    try:
        info = PRIVATE_GAME_LABELS.get(o.get("game", ""), ("O'yin", 0))
        await bot.send_message(
            o["user_id"],
            f"🎉 **Privat serveringiz ochildi!**\n\n"
            f"🎮 O'yin: **{info[0]}**\n"
            f"👤 Nik: `{esc_md(o.get('roblox_nick',''))}`\n\n"
            f"✅ Robloxga kirib tekshirishingiz mumkin.\n"
            f"👥 Lord\\_plays77 shunga druzya tashlang — privatga qo'shmoqchi bo'lgan akkountlaringizdan!",
            reply_markup=main_kb(user_lang)
        )
    except Exception:
        pass
    try:
        await cb.message.edit_text(cb.message.text + f"\n\n✅ TASDIQLANDI ({now()})")
    except Exception:
        pass
    await cb.answer("✅ Tasdiqlandi!")

@dp.callback_query(F.data.startswith("ps_no_"))
async def ps_admin_no(cb: types.CallbackQuery):
    if not is_referral_admin(cb.from_user.id):
        return
    oid = cb.data[len("ps_no_"):]
    o   = await reject_private_order(oid)
    if not o:
        await cb.answer("Allaqachon ko'rilgan!", show_alert=True)
        return
    user_lang = await get_user_lang(o["user_id"])
    try:
        await bot.send_message(
            o["user_id"],
            f"❌ **Admin so'rovingizni rad etdi.**\n\n"
            f"🔄 Referallaringiz hisobingizga qaytarildi: **+{o.get('ref_cost', 0)} ta**",
            reply_markup=main_kb(user_lang)
        )
    except Exception:
        pass
    try:
        await cb.message.edit_text(cb.message.text + f"\n\n❌ RAD ETILDI + referallar qaytarildi ({now()})")
    except Exception:
        pass
    await cb.answer("❌ Rad etildi!")

# ═══════════════════════════════════════════════════════
# 🏆 REYTING BO'LIMI
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: msg.text in ["🏆 Reyting", "🏆 Rating", "🏆 Рейтинг"]))
async def cmd_leaderboard(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    top = await get_top_referrals(20)
    if not top:
        await msg.answer("🏆 Hozircha reyting bo'sh.", reply_markup=main_kb(await get_user_lang(msg.from_user.id)))
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 **TOP 20 — Referal Reytingi**\n━━━━━━━━━━━━━━━━━━━━"]
    for i, u in enumerate(top, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        uname = u.get("username") or "-"
        cnt   = u.get("ref_count", 0)
        lines.append(f"{medal} @{uname} — **{cnt}** referal")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    await msg.answer("\n".join(lines), reply_markup=main_kb(await get_user_lang(msg.from_user.id)))

# ═══════════════════════════════════════════════════════
# ✅ ISBOTLAR BO'LIMI
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_proofs") for l in LANGS)))
async def cmd_proofs(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    await send_event_sticker(msg.chat.id, "proofs")
    lang = await get_user_lang(msg.from_user.id)
    b = InlineKeyboardBuilder()
    b.button(text="✅ Isbotlar kanali", url=f"https://t.me/{PROOFS_CHANNEL.lstrip('@')}")
    b.adjust(1)
    await msg.answer(
        f"✅ *Isbotlar*\n\n"
        f"Bajarilgan buyurtmalar va mijozlarimizning fikr-mulohazalarini "
        f"{esc_md(PROOFS_CHANNEL)} kanalidan ko'rishingiz mumkin:",
        reply_markup=b.as_markup()
    )

# ═══════════════════════════════════════════════════════
# 🤖 AI YORDAMCHI (shaxsiy Telegram akkauntini ulash orqali
# avto javob va avto xabar tizimi) — Telethon asosida
# ═══════════════════════════════════════════════════════

# ── FSM holatlari ──
class UserbotConnect(StatesGroup):
    phone    = State()
    code     = State()
    password = State()

class AutoReplySetup(StatesGroup):
    photo      = State()
    gifsticker = State()
    text       = State()

class AutoBroadcastSetup(StatesGroup):
    content        = State()
    interval_unit  = State()
    interval_value = State()

# Login jarayonida vaqtinchalik Telethon client'lar (xotirada, DB'ga yozilmaydi)
PENDING_LOGIN: dict[int, dict] = {}
# Avto javobda spam/loop bo'lmasligi uchun tashqi cooldown: {(owner_uid, sender_id): last_ts}
REPLY_THROTTLE: dict[tuple, float] = {}
REPLY_THROTTLE_SECONDS = 6 * 3600  # bir xil odamga 6 soatda bir marta avto javob


async def download_bytes(file_id: str) -> bytes:
    """Aiogram bot orqali faylni yuklab, xotiradagi bayt sifatida qaytaradi
    (Telethon'ga qayta yuklash uchun, chunki Bot API file_id userbot'da ishlamaydi)."""
    buf = await bot.download(file_id)
    return buf.read()


# ── Userbot (Telethon) menejeri ──
class UserbotManager:
    def __init__(self):
        self.clients: dict[int, TelegramClient] = {}

    def get_client(self, uid: int):
        return self.clients.get(uid)

    async def stop_client_for_user(self, uid: int):
        client = self.clients.pop(uid, None)
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass

    async def start_client_for_user(self, uid: int, session_str: str):
        await self.stop_client_for_user(uid)
        try:
            client = TelegramClient(StringSession(session_str), TELETHON_API_ID, TELETHON_API_HASH)
            await client.connect()
            if not await client.is_user_authorized():
                logging.warning(f"⚠️ Userbot {uid}: sessiya avtorizatsiyadan o'tmagan, o'chirib qo'yildi.")
                await client.disconnect()
                await userbot_accounts.delete_one({"user_id": uid})
                return None
            client.add_event_handler(self._make_autoreply_handler(uid), events.NewMessage(incoming=True))
            self.clients[uid] = client
            logging.info(f"✅ Userbot ishga tushdi: {uid}")
            return client
        except Exception as e:
            logging.error(f"Userbot ulanmadi ({uid}): {e}")
            return None

    def _make_autoreply_handler(self, uid: int):
        async def handler(event):
            try:
                if not event.is_private:
                    return
                sender = await event.get_sender()
                if sender is None or getattr(sender, "bot", False):
                    return
                settings = await autoreply_col.find_one({"user_id": uid, "enabled": True})
                if not settings:
                    return
                key = (uid, event.sender_id)
                last = REPLY_THROTTLE.get(key, 0)
                if datetime.now().timestamp() - last < REPLY_THROTTLE_SECONDS:
                    return
                REPLY_THROTTLE[key] = datetime.now().timestamp()
                client = self.clients.get(uid)
                if not client:
                    return
                if settings.get("photo_b64"):
                    bio = BytesIO(base64.b64decode(settings["photo_b64"]))
                    bio.name = "photo.jpg"
                    await client.send_file(event.chat_id, bio)
                if settings.get("media_b64"):
                    kind = settings.get("media_kind", "animation")
                    bio = BytesIO(base64.b64decode(settings["media_b64"]))
                    bio.name = "sticker.webp" if kind == "sticker" else "gif.mp4"
                    await client.send_file(event.chat_id, bio)
                if settings.get("text"):
                    await client.send_message(event.chat_id, settings["text"])
            except Exception as e:
                logging.error(f"Avto javob xatosi ({uid}): {e}")
        return handler

    async def restart_all(self):
        async for acc in userbot_accounts.find({}):
            try:
                session_str = decrypt_session(acc["session_enc"])
                await self.start_client_for_user(acc["user_id"], session_str)
            except Exception as e:
                logging.error(f"Userbot qayta ulanmadi ({acc.get('user_id')}): {e}")


userbot_manager = UserbotManager()


async def _cleanup_pending_login(uid: int):
    pend = PENDING_LOGIN.pop(uid, None)
    if pend:
        try:
            await pend["client"].disconnect()
        except Exception:
            pass


async def _finish_login(msg: types.Message, state: FSMContext, uid: int):
    lang = await get_user_lang(uid)
    pend = PENDING_LOGIN.pop(uid, None)
    if not pend:
        await state.clear()
        return
    client = pend["client"]
    session_str = client.session.save()
    try:
        await client.disconnect()
    except Exception:
        pass
    await userbot_accounts.update_one(
        {"user_id": uid},
        {"$set": {
            "user_id": uid, "phone": pend["phone"],
            "session_enc": encrypt_session(session_str), "connected_at": now(),
        }},
        upsert=True
    )
    await userbot_manager.start_client_for_user(uid, session_str)
    await state.clear()
    await msg.answer("✅ Akkaunt muvaffaqiyatli ulandi!", reply_markup=main_kb(lang))
    await show_ai_menu(msg.chat.id, uid)


async def show_ai_menu(chat_id: int, uid: int):
    acc = await userbot_accounts.find_one({"user_id": uid})
    b = InlineKeyboardBuilder()
    if not acc:
        b.button(text="🔗 Akkaunt ulash", callback_data="ub_connect")
        b.adjust(1)
        text = (
            "🤖 *AI Yordamchi*\n\n"
            "Bu bo'limda shaxsiy Telegram akkauntingizni ulab:\n"
            "🔁 Yozgan odamlarga *avto javob* berishni,\n"
            "📢 Kanallaringizga *avto xabar* yuborishni sozlashingiz mumkin.\n\n"
            "⚠️ Davom etish uchun avval akkauntingizni ulang:"
        )
    else:
        b.button(text="🔁 Avto javob", callback_data="ar_menu")
        b.button(text="📢 Avto xabar", callback_data="bc_menu")
        b.button(text="🔌 Akkauntni uzish", callback_data="ub_disconnect")
        b.adjust(2, 1)
        text = (
            f"🤖 *AI Yordamchi*\n\n✅ Ulangan akkaunt: `{esc_md(acc.get('phone',''))}`\n\n"
            "Kerakli bo'limni tanlang:"
        )
    await bot.send_message(chat_id, text, reply_markup=b.as_markup())


@dp.message(F.text == "🤖 AI Yordamchi")
async def cmd_ai_yordamchi(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    await show_ai_menu(msg.chat.id, msg.from_user.id)


@dp.callback_query(F.data == "ai_back")
async def ai_back(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await show_ai_menu(cb.message.chat.id, cb.from_user.id)
    await cb.answer()


@dp.callback_query(F.data == "generic_cancel")
async def generic_cancel(cb: types.CallbackQuery, state: FSMContext):
    lang = await get_user_lang(cb.from_user.id)
    await state.clear()
    await cb.message.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
    await cb.answer()


# ── Akkauntni ulash (telefon raqami orqali) ──
@dp.callback_query(F.data == "ub_connect")
async def ub_connect_start(cb: types.CallbackQuery, state: FSMContext):
    if not TELETHON_API_ID or not TELETHON_API_HASH:
        await cb.answer("⚠️ TELETHON_API_ID / TELETHON_API_HASH sozlanmagan (.env)!", show_alert=True)
        return
    lang = await get_user_lang(cb.from_user.id)
    await cb.message.answer(
        "📱 Telegram akkauntingiz raqamini xalqaro formatda yuboring.\n"
        "Masalan: `+998901234567`",
        reply_markup=cancel_kb(lang)
    )
    await state.set_state(UserbotConnect.phone)
    await cb.answer()


@dp.message(UserbotConnect.phone)
async def ub_got_phone(msg: types.Message, state: FSMContext):
    uid, lang = msg.from_user.id, await get_user_lang(msg.from_user.id)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    phone = (msg.text or "").strip().replace(" ", "")
    if not phone.startswith("+") or not phone[1:].isdigit() or len(phone) < 8:
        await msg.answer("❌ Raqam noto'g'ri formatda. Masalan: +998901234567\nQaytadan yuboring:")
        return
    wait_msg = await msg.answer("⏳ Kod yuborilmoqda...")
    client = TelegramClient(StringSession(), TELETHON_API_ID, TELETHON_API_HASH)
    try:
        await client.connect()
        sent = await client.send_code_request(phone)
    except FloodWaitError as e:
        await wait_msg.edit_text(f"❌ Juda ko'p urinish qilindi. {e.seconds} soniyadan keyin qaytadan urining.")
        await state.clear()
        return
    except PhoneNumberInvalidError:
        await wait_msg.edit_text("❌ Bu raqam noto'g'ri. Qaytadan urinib ko'ring.")
        await state.clear()
        return
    except Exception as e:
        logging.error(f"send_code_request xatosi: {e}")
        await wait_msg.edit_text("❌ Xatolik yuz berdi, birozdan keyin qaytadan urinib ko'ring.")
        await state.clear()
        return
    PENDING_LOGIN[uid] = {"client": client, "phone": phone, "phone_code_hash": sent.phone_code_hash}
    type_name = type(sent.type).__name__
    logging.info(f"send_code_request natijasi ({phone}): {type_name}")
    if "Call" in type_name:
        method_txt = "☎️ *Qo'ng'iroq orqali* yuboriladi — telefoningizga qo'ng'iroq keladi, охирги 4 ta raqam kod bo'ladi."
    elif "Sms" in type_name:
        method_txt = "📩 *SMS orqali* yuborildi — SMS xabarlaringizni tekshiring."
    elif "App" in type_name:
        method_txt = "📲 *Telegram ilovasi orqali* yuborildi — ilovadagi \"Telegram\" rasmiy xabarlar chatini tekshiring."
    else:
        method_txt = f"ℹ️ Yuborish usuli: {type_name}"
    rb = InlineKeyboardBuilder()
    rb.button(text="🔁 SMS orqali qayta yuborish", callback_data="ub_resend_sms")
    rb.adjust(1)
    await wait_msg.edit_text(
        f"🔑 Kod yuborildi.\n{method_txt}\n\nKelgan kodni shu yerga kiriting:",
        reply_markup=rb.as_markup()
    )
    await state.set_state(UserbotConnect.code)


@dp.callback_query(F.data == "ub_resend_sms")
async def ub_resend_sms(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    pend = PENDING_LOGIN.get(uid)
    if not pend:
        await cb.answer("Sessiya tugagan, qaytadan boshlang.", show_alert=True)
        return
    try:
        # Telethon phone_code_hash'ni client ichida o'zi keshlab saqlaydi,
        # shuning uchun uni qo'lda uzatish kerak emas (va bunday parametr
        # send_code_request() da umuman mavjud emas). Oddiy qayta chaqiruv
        # avtomatik ravishda ResendCodeRequest so'rovini yuboradi.
        sent = await pend["client"].send_code_request(pend["phone"])
        pend["phone_code_hash"] = sent.phone_code_hash
        type_name = type(sent.type).__name__
        if "Sms" in type_name:
            txt = "📩 SMS qayta yuborildi!"
        elif "Call" in type_name:
            txt = "☎️ Qo'ng'iroq orqali kod yuborildi!"
        elif "App" in type_name:
            txt = "📲 Kod ilova orqali yuborildi (bu raqam uchun boshqa usul mavjud emas)."
        else:
            txt = f"ℹ️ Kod qayta yuborildi ({type_name})."
        await cb.answer(txt, show_alert=True)
    except FloodWaitError as e:
        await cb.answer(f"❌ Juda ko'p urinish. {e.seconds} soniyadan keyin urining.", show_alert=True)
    except SendCodeUnavailableError:
        await cb.answer(
            "❌ Bu raqam uchun barcha yuborish usullari (flash-call, SMS) allaqachon "
            "ishlatilgan. Kod Telegram ilovangizdagi \"Telegram\" rasmiy xabarlar "
            "bo'limida bo'lishi mumkin, yoki birozdan keyin qaytadan urinib ko'ring.",
            show_alert=True
        )
    except Exception as e:
        logging.error(f"resend xatosi: {e}")
        await cb.answer("❌ Xatolik yuz berdi.", show_alert=True)


@dp.message(UserbotConnect.code)
async def ub_got_code(msg: types.Message, state: FSMContext):
    uid, lang = msg.from_user.id, await get_user_lang(msg.from_user.id)
    if msg.text == T(lang, "cancel"):
        await _cleanup_pending_login(uid)
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    pend = PENDING_LOGIN.get(uid)
    if not pend:
        await state.clear()
        await msg.answer("❌ Sessiya tugagan, qaytadan boshlang.", reply_markup=main_kb(lang))
        return
    code = (msg.text or "").strip().replace(" ", "")
    client = pend["client"]
    try:
        await client.sign_in(phone=pend["phone"], code=code, phone_code_hash=pend["phone_code_hash"])
    except SessionPasswordNeededError:
        await msg.answer("🔒 Akkauntingizda 2 bosqichli parol yoqilgan. Parolni kiriting:")
        await state.set_state(UserbotConnect.password)
        return
    except (PhoneCodeInvalidError, PhoneCodeExpiredError):
        await msg.answer("❌ Kod noto'g'ri yoki muddati tugagan. Qaytadan kiriting:")
        return
    except Exception as e:
        logging.error(f"sign_in xatosi: {e}")
        await msg.answer("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring (/start).")
        await _cleanup_pending_login(uid)
        await state.clear()
        return
    await _finish_login(msg, state, uid)


@dp.message(UserbotConnect.password)
async def ub_got_password(msg: types.Message, state: FSMContext):
    uid, lang = msg.from_user.id, await get_user_lang(msg.from_user.id)
    if msg.text == T(lang, "cancel"):
        await _cleanup_pending_login(uid)
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    pend = PENDING_LOGIN.get(uid)
    if not pend:
        await state.clear()
        await msg.answer("❌ Sessiya tugagan, qaytadan boshlang.", reply_markup=main_kb(lang))
        return
    try:
        await pend["client"].sign_in(password=(msg.text or "").strip())
    except PasswordHashInvalidError:
        await msg.answer("❌ Parol noto'g'ri. Qaytadan kiriting:")
        return
    except Exception as e:
        logging.error(f"2FA sign_in xatosi: {e}")
        await msg.answer("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring (/start).")
        await _cleanup_pending_login(uid)
        await state.clear()
        return
    await _finish_login(msg, state, uid)


@dp.callback_query(F.data == "ub_disconnect")
async def ub_disconnect(cb: types.CallbackQuery):
    uid = cb.from_user.id
    await userbot_manager.stop_client_for_user(uid)
    await userbot_accounts.delete_one({"user_id": uid})
    await autoreply_col.update_one({"user_id": uid}, {"$set": {"enabled": False}})
    await autobroadcast_col.update_many({"user_id": uid}, {"$set": {"active": False}})
    await cb.message.answer("🔌 Akkaunt uzildi.")
    await cb.answer()


# ── 🔁 AVTO JAVOB ──
@dp.callback_query(F.data == "ar_menu")
async def ar_menu(cb: types.CallbackQuery):
    uid = cb.from_user.id
    acc = await userbot_accounts.find_one({"user_id": uid})
    if not acc:
        await cb.answer("Avval akkaunt ulang!", show_alert=True)
        return
    settings = await autoreply_col.find_one({"user_id": uid})
    b = InlineKeyboardBuilder()
    if settings:
        state_txt = "✅ Yoqilgan" if settings.get("enabled") else "🚫 O'chirilgan"
        toggle_txt = "🚫 O'chirish" if settings.get("enabled") else "✅ Yoqish"
        b.button(text="✏️ Qayta sozlash", callback_data="ar_setup_start")
        b.button(text=toggle_txt, callback_data="ar_toggle")
    else:
        state_txt = "Sozlanmagan"
        b.button(text="➕ Sozlash", callback_data="ar_setup_start")
    b.button(text="⬅️ Orqaga", callback_data="ai_back")
    b.adjust(1)
    await cb.message.answer(f"🔁 *Avto javob*\n\nHolati: {state_txt}", reply_markup=b.as_markup())
    await cb.answer()


@dp.callback_query(F.data == "ar_toggle")
async def ar_toggle(cb: types.CallbackQuery):
    uid = cb.from_user.id
    settings = await autoreply_col.find_one({"user_id": uid})
    if not settings:
        await cb.answer("Avval sozlang!", show_alert=True)
        return
    new_val = not settings.get("enabled", False)
    await autoreply_col.update_one({"user_id": uid}, {"$set": {"enabled": new_val}})
    await cb.answer("✅ Yoqildi!" if new_val else "🚫 O'chirildi!")
    await ar_menu(cb)


@dp.callback_query(F.data == "ar_setup_start")
async def ar_setup_start(cb: types.CallbackQuery, state: FSMContext):
    lang = await get_user_lang(cb.from_user.id)
    await state.update_data(ar_photo=None, ar_media=None, ar_media_kind=None)
    await cb.message.answer("📸 Avto javobda ko'rsatiladigan rasm yuboring (ixtiyoriy):", reply_markup=skip_cancel_kb(lang))
    await state.set_state(AutoReplySetup.photo)
    await cb.answer()


@dp.message(AutoReplySetup.photo, F.photo)
async def ar_photo_got(msg: types.Message, state: FSMContext):
    lang = await get_user_lang(msg.from_user.id)
    raw = await download_bytes(msg.photo[-1].file_id)
    await state.update_data(ar_photo=base64.b64encode(raw).decode())
    await msg.answer("🎞 Endi GIF yoki stiker yuboring (ixtiyoriy):", reply_markup=skip_cancel_kb(lang))
    await state.set_state(AutoReplySetup.gifsticker)


@dp.message(AutoReplySetup.photo)
async def ar_photo_skip(msg: types.Message, state: FSMContext):
    lang = await get_user_lang(msg.from_user.id)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await msg.answer("🎞 Endi GIF yoki stiker yuboring (ixtiyoriy):", reply_markup=skip_cancel_kb(lang))
    await state.set_state(AutoReplySetup.gifsticker)


@dp.message(AutoReplySetup.gifsticker, F.animation)
async def ar_anim_got(msg: types.Message, state: FSMContext):
    raw = await download_bytes(msg.animation.file_id)
    await state.update_data(ar_media=base64.b64encode(raw).decode(), ar_media_kind="animation")
    await _ar_ask_text(msg, state)


@dp.message(AutoReplySetup.gifsticker, F.sticker)
async def ar_sticker_got(msg: types.Message, state: FSMContext):
    raw = await download_bytes(msg.sticker.file_id)
    await state.update_data(ar_media=base64.b64encode(raw).decode(), ar_media_kind="sticker")
    await _ar_ask_text(msg, state)


@dp.message(AutoReplySetup.gifsticker)
async def ar_gifsticker_skip(msg: types.Message, state: FSMContext):
    lang = await get_user_lang(msg.from_user.id)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await _ar_ask_text(msg, state)


async def _ar_ask_text(msg: types.Message, state: FSMContext):
    lang = await get_user_lang(msg.from_user.id)
    await msg.answer("📝 Endi avto javob matnini yozing (bu qism *majburiy*):", reply_markup=cancel_kb(lang))
    await state.set_state(AutoReplySetup.text)


@dp.message(AutoReplySetup.text)
async def ar_text_got(msg: types.Message, state: FSMContext):
    lang = await get_user_lang(msg.from_user.id)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    text = (msg.text or "").strip()
    if not text:
        await msg.answer("❌ Matn bo'sh bo'lmasin, qaytadan yozing:")
        return
    await state.update_data(ar_text=text)
    d = await state.get_data()
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data="ar_confirm")
    b.button(text="❌ Bekor qilish", callback_data="generic_cancel")
    b.adjust(2)
    preview = []
    if d.get("ar_photo"):
        preview.append("📸 Rasm: bor")
    if d.get("ar_media"):
        preview.append(f"🎞 Media: bor ({d.get('ar_media_kind')})")
    preview.append(f"📝 Matn: {esc_md(text)}")
    await msg.answer("👀 *Ko'rib chiqing:*\n\n" + "\n".join(preview), reply_markup=b.as_markup())


@dp.callback_query(F.data == "ar_confirm")
async def ar_confirm(cb: types.CallbackQuery, state: FSMContext):
    uid, lang = cb.from_user.id, await get_user_lang(cb.from_user.id)
    d = await state.get_data()
    await autoreply_col.update_one(
        {"user_id": uid},
        {"$set": {
            "user_id": uid,
            "photo_b64": d.get("ar_photo"),
            "media_b64": d.get("ar_media"),
            "media_kind": d.get("ar_media_kind"),
            "text": d.get("ar_text", ""),
            "enabled": True,
            "updated_at": now(),
        }},
        upsert=True
    )
    await state.clear()
    await cb.message.answer("✅ Avto javob sozlandi va yoqildi!", reply_markup=main_kb(lang))
    await cb.answer()


# ── 📢 AVTO XABAR ──
@dp.callback_query(F.data == "bc_menu")
async def bc_menu(cb: types.CallbackQuery):
    uid = cb.from_user.id
    acc = await userbot_accounts.find_one({"user_id": uid})
    if not acc:
        await cb.answer("Avval akkaunt ulang!", show_alert=True)
        return
    configs = await autobroadcast_col.find({"user_id": uid}).to_list(length=20)
    b = InlineKeyboardBuilder()
    b.button(text="➕ Yangi avto xabar", callback_data="bc_new")
    for c in configs:
        status = "✅" if c.get("active") else "🚫"
        titles = ", ".join(ch["title"] for ch in c.get("channels", [])[:2]) or "kanal"
        b.button(text=f"{status} {titles}", callback_data=f"bc_view_{c['_id']}")
    b.button(text="⬅️ Orqaga", callback_data="ai_back")
    b.adjust(1)
    await cb.message.answer("📢 *Avto xabar*\n\nMavjud sozlamalar yoki yangisini qo'shing:", reply_markup=b.as_markup())
    await cb.answer()


@dp.callback_query(F.data.startswith("bc_view_"))
async def bc_view(cb: types.CallbackQuery):
    cid = cb.data[len("bc_view_"):]
    cfg = await autobroadcast_col.find_one({"_id": ObjectId(cid)})
    if not cfg or cfg["user_id"] != cb.from_user.id:
        await cb.answer("Topilmadi!", show_alert=True)
        return
    titles = "\n".join(f"• {esc_md(ch['title'])}" for ch in cfg.get("channels", []))
    interval = cfg.get("interval_seconds", 0)
    interval_txt = f"{interval // 3600} soat" if interval % 3600 == 0 and interval >= 3600 else f"{interval // 60} daqiqa"
    status = "✅ Faol" if cfg.get("active") else "🚫 To'xtatilgan"
    b = InlineKeyboardBuilder()
    toggle_txt = "🛑 To'xtatish" if cfg.get("active") else "▶️ Qayta yoqish"
    b.button(text=toggle_txt, callback_data=f"bc_toggle_{cid}")
    b.button(text="🗑 O'chirish", callback_data=f"bc_del_{cid}")
    b.button(text="⬅️ Orqaga", callback_data="bc_menu")
    b.adjust(1)
    await cb.message.answer(
        f"📢 *Avto xabar sozlamasi*\n\nHolati: {status}\n⏱ Interval: {interval_txt}\n\nKanallar:\n{titles}",
        reply_markup=b.as_markup()
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("bc_toggle_"))
async def bc_toggle(cb: types.CallbackQuery):
    cid = cb.data[len("bc_toggle_"):]
    cfg = await autobroadcast_col.find_one({"_id": ObjectId(cid)})
    if not cfg or cfg["user_id"] != cb.from_user.id:
        await cb.answer("Topilmadi!", show_alert=True)
        return
    new_active = not cfg.get("active", False)
    update = {"active": new_active}
    if new_active:
        update["next_run"] = datetime.now() + timedelta(seconds=cfg["interval_seconds"])
    await autobroadcast_col.update_one({"_id": cfg["_id"]}, {"$set": update})
    await cb.answer("✅ Yoqildi!" if new_active else "🚫 To'xtatildi!")
    await bc_view(cb)


@dp.callback_query(F.data.startswith("bc_del_"))
async def bc_del(cb: types.CallbackQuery):
    cid = cb.data[len("bc_del_"):]
    cfg = await autobroadcast_col.find_one({"_id": ObjectId(cid)})
    if not cfg or cfg["user_id"] != cb.from_user.id:
        await cb.answer("Topilmadi!", show_alert=True)
        return
    await autobroadcast_col.delete_one({"_id": cfg["_id"]})
    await cb.answer("🗑 O'chirildi!")
    try:
        await cb.message.edit_text("🗑 O'chirildi.")
    except Exception:
        pass


@dp.callback_query(F.data == "bc_new")
async def bc_new(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    client = userbot_manager.get_client(uid)
    if not client:
        await cb.answer("Akkaunt ulanmagan yoki offline!", show_alert=True)
        return
    await cb.answer("⏳ Kanallar yuklanmoqda...")
    channels = []
    async for dialog in client.iter_dialogs(limit=100):
        ent = dialog.entity
        if isinstance(ent, Channel) or isinstance(ent, Chat):
            channels.append({"id": ent.id, "access_hash": getattr(ent, "access_hash", 0), "title": dialog.title})
    if not channels:
        await cb.message.answer("❌ Hech qanday kanal yoki guruh topilmadi.")
        return
    await state.update_data(bc_all_channels=channels, bc_selected=[])
    await _render_channel_picker(cb.message, state)


async def _render_channel_picker(msg: types.Message, state: FSMContext):
    d = await state.get_data()
    all_ch = d.get("bc_all_channels", [])
    selected = set(d.get("bc_selected", []))
    b = InlineKeyboardBuilder()
    for i, ch in enumerate(all_ch[:30]):
        mark = "✅ " if ch["id"] in selected else ""
        b.button(text=f"{mark}{ch['title'][:30]}", callback_data=f"bc_pick_{i}")
    b.button(text="➡️ Davom etish", callback_data="bc_pick_done")
    b.button(text="❌ Bekor qilish", callback_data="generic_cancel")
    b.adjust(1)
    await msg.answer(f"📢 Kanallarni tanlang ({len(selected)} ta tanlandi):", reply_markup=b.as_markup())


@dp.callback_query(F.data == "bc_pick_done")
async def bc_pick_done(cb: types.CallbackQuery, state: FSMContext):
    d = await state.get_data()
    selected_ids = set(d.get("bc_selected", []))
    if not selected_ids:
        await cb.answer("Kamida 1 ta kanal tanlang!", show_alert=True)
        return
    all_ch = d.get("bc_all_channels", [])
    chosen = [c for c in all_ch if c["id"] in selected_ids]
    await state.update_data(bc_chosen=chosen)
    lang = await get_user_lang(cb.from_user.id)
    await cb.message.answer("✍️ Yubormoqchi bo'lgan xabaringizni yuboring (matn, rasm, video va h.k.):", reply_markup=cancel_kb(lang))
    await state.set_state(AutoBroadcastSetup.content)
    await cb.answer()


@dp.callback_query(F.data.startswith("bc_pick_"))
async def bc_pick(cb: types.CallbackQuery, state: FSMContext):
    idx_str = cb.data[len("bc_pick_"):]
    if not idx_str.isdigit():
        await cb.answer()
        return
    idx = int(idx_str)
    d = await state.get_data()
    all_ch = d.get("bc_all_channels", [])
    selected = list(d.get("bc_selected", []))
    if idx >= len(all_ch):
        await cb.answer()
        return
    ch_id = all_ch[idx]["id"]
    if ch_id in selected:
        selected.remove(ch_id)
    else:
        selected.append(ch_id)
    await state.update_data(bc_selected=selected)
    await cb.answer()
    await _render_channel_picker(cb.message, state)


@dp.message(AutoBroadcastSetup.content)
async def bc_content_got(msg: types.Message, state: FSMContext):
    lang = await get_user_lang(msg.from_user.id)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    content = None
    if msg.photo:
        raw = await download_bytes(msg.photo[-1].file_id)
        content = {"type": "photo", "media_b64": base64.b64encode(raw).decode(), "filename": "photo.jpg", "caption": msg.caption or ""}
    elif msg.video:
        raw = await download_bytes(msg.video.file_id)
        content = {"type": "video", "media_b64": base64.b64encode(raw).decode(), "filename": "video.mp4", "caption": msg.caption or ""}
    elif msg.animation:
        raw = await download_bytes(msg.animation.file_id)
        content = {"type": "animation", "media_b64": base64.b64encode(raw).decode(), "filename": "anim.mp4", "caption": msg.caption or ""}
    elif msg.text:
        content = {"type": "text", "text": msg.text}
    else:
        await msg.answer("❌ Bu turdagi xabar qo'llab-quvvatlanmaydi. Matn, rasm yoki video yuboring:")
        return
    await state.update_data(bc_content=content)
    b = InlineKeyboardBuilder()
    b.button(text="⏱ Daqiqa", callback_data="bc_unit_min")
    b.button(text="🕐 Soat", callback_data="bc_unit_hour")
    b.adjust(2)
    await msg.answer("⏱ Xabar necha daqiqada yoki soatda bir marta yuborilsin?", reply_markup=b.as_markup())
    await state.set_state(AutoBroadcastSetup.interval_unit)


@dp.callback_query(F.data == "bc_unit_min")
async def bc_unit_min(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(bc_unit="min")
    await cb.message.answer("🔢 Necha daqiqada bir marta yuborilsin? Raqam kiriting (masalan: 30):")
    await state.set_state(AutoBroadcastSetup.interval_value)
    await cb.answer()


@dp.callback_query(F.data == "bc_unit_hour")
async def bc_unit_hour(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(bc_unit="hour")
    await cb.message.answer("🔢 Necha soatda bir marta yuborilsin? Raqam kiriting (masalan: 3):")
    await state.set_state(AutoBroadcastSetup.interval_value)
    await cb.answer()


@dp.message(AutoBroadcastSetup.interval_value)
async def bc_interval_value(msg: types.Message, state: FSMContext):
    uid, lang = msg.from_user.id, await get_user_lang(msg.from_user.id)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    txt = (msg.text or "").strip()
    if not txt.isdigit() or int(txt) <= 0:
        await msg.answer("❌ Faqat musbat raqam kiriting:")
        return
    value = int(txt)
    d = await state.get_data()
    unit = d.get("bc_unit", "min")
    interval_seconds = value * 60 if unit == "min" else value * 3600
    chosen = d.get("bc_chosen", [])
    content = d.get("bc_content")
    if not chosen or not content:
        await state.clear()
        await msg.answer("❌ Xatolik: ma'lumot yetarli emas, qaytadan urinib ko'ring.", reply_markup=main_kb(lang))
        return
    await autobroadcast_col.insert_one({
        "user_id": uid,
        "channels": chosen,
        "content": content,
        "interval_seconds": interval_seconds,
        "next_run": datetime.now() + timedelta(seconds=interval_seconds),
        "active": True,
        "created_at": now(),
    })
    await state.clear()
    unit_txt = "daqiqa" if unit == "min" else "soat"
    await msg.answer(
        f"✅ Avto xabar sozlandi! Har {value} {unit_txt}da {len(chosen)} ta kanalga yuboriladi.",
        reply_markup=main_kb(lang)
    )


async def broadcast_scheduler_loop():
    """Har 30 soniyada DB'ni tekshirib, vaqti kelgan avto xabarlarni yuboradi."""
    while True:
        try:
            now_ts = datetime.now()
            async for cfg in autobroadcast_col.find({"active": True, "next_run": {"$lte": now_ts}}):
                client = userbot_manager.get_client(cfg["user_id"])
                if not client:
                    continue
                content = cfg.get("content", {})
                for ch in cfg.get("channels", []):
                    try:
                        entity = InputPeerChannel(ch["id"], ch["access_hash"])
                        if content.get("type") == "text":
                            await client.send_message(entity, content.get("text", ""))
                        else:
                            raw = base64.b64decode(content["media_b64"])
                            bio = BytesIO(raw)
                            bio.name = content.get("filename", "file.dat")
                            await client.send_file(entity, bio, caption=content.get("caption") or None)
                    except Exception as e:
                        logging.error(f"Avto xabar yuborishda xato ({cfg['user_id']} -> {ch.get('title')}): {e}")
                await autobroadcast_col.update_one(
                    {"_id": cfg["_id"]},
                    {"$set": {
                        "next_run": now_ts + timedelta(seconds=cfg["interval_seconds"]),
                        "last_run": now(),
                    }}
                )
        except Exception as e:
            logging.error(f"Broadcast scheduler xatosi: {e}")
        await asyncio.sleep(30)


# ═══════════════════════════════════════════════════════
# TRADE / DUEL / SOTUV — BIRLASHTIRILGAN MENYU
# (har biri bosilganda 2 ta bo'lim chiqadi: Qo'shish / Ko'rish)
# ═══════════════════════════════════════════════════════
@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_trade_menu") for l in LANGS)))
async def cmd_trade_menu(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    lang = await get_user_lang(msg.from_user.id)
    b = InlineKeyboardBuilder()
    b.button(text=T(lang, "menu_add"), callback_data="menu_trade_add")
    b.button(text=T(lang, "menu_view"), callback_data="menu_trade_view")
    b.adjust(2)
    await msg.answer(f"{T(lang, 'btn_trade_menu')}\n\n👇 Bo'limni tanlang:", reply_markup=b.as_markup())

@dp.callback_query(F.data == "menu_trade_add")
async def cb_menu_trade_add(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await cmd_trade_add(_as_user_msg(cb), state)

@dp.callback_query(F.data == "menu_trade_view")
async def cb_menu_trade_view(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await cmd_trades(_as_user_msg(cb), state)

@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_duel_menu") for l in LANGS)))
async def cmd_duel_menu(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    lang = await get_user_lang(msg.from_user.id)
    b = InlineKeyboardBuilder()
    b.button(text=T(lang, "menu_add"), callback_data="menu_duel_add")
    b.button(text=T(lang, "menu_view"), callback_data="menu_duel_view")
    b.adjust(2)
    await msg.answer(f"{T(lang, 'btn_duel_menu')}\n\n👇 Bo'limni tanlang:", reply_markup=b.as_markup())

@dp.callback_query(F.data == "menu_duel_add")
async def cb_menu_duel_add(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await cmd_duel_add(_as_user_msg(cb), state)

@dp.callback_query(F.data == "menu_duel_view")
async def cb_menu_duel_view(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await cmd_duel_list(_as_user_msg(cb), state)

@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_sotuv_menu") for l in LANGS)))
async def cmd_sotuv_menu(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    lang = await get_user_lang(msg.from_user.id)
    b = InlineKeyboardBuilder()
    b.button(text=T(lang, "menu_add"), callback_data="menu_sale_add")
    b.button(text=T(lang, "menu_view"), callback_data="menu_sale_view")
    b.adjust(2)
    await msg.answer(f"{T(lang, 'btn_sotuv_menu')}\n\n👇 Bo'limni tanlang:", reply_markup=b.as_markup())

@dp.callback_query(F.data == "menu_sale_add")
async def cb_menu_sale_add(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await cmd_sale_add(_as_user_msg(cb), state)

@dp.callback_query(F.data == "menu_sale_view")
async def cb_menu_sale_view(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    await cmd_sales(_as_user_msg(cb), state)


# ═══════════════════════════════════════════════════════
# AKKAUNTLAR BO'LIMI (Akkount olish / Akkount sotish)
# ═══════════════════════════════════════════════════════
accounts_col = mdb["accounts"]

class AccountSell(StatesGroup):
    name  = State()
    photo = State()
    price = State()
    bio   = State()

async def active_accounts():
    return await accounts_col.find({"active": True}).sort("created_at", -1).to_list(length=200)

@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_accounts_menu") for l in LANGS)))
async def cmd_accounts_menu(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    lang = await get_user_lang(msg.from_user.id)
    b = InlineKeyboardBuilder()
    b.button(text=T(lang, "acc_buy"), callback_data="acc_buy")
    b.button(text=T(lang, "acc_sell"), callback_data="acc_sell")
    b.adjust(2)
    await msg.answer(f"{T(lang, 'btn_accounts_menu')}\n\n👇 Bo'limni tanlang:", reply_markup=b.as_markup())

@dp.callback_query(F.data == "acc_sell")
async def cb_acc_sell(cb: types.CallbackQuery, state: FSMContext):
    lang = await get_user_lang(cb.from_user.id)
    await cb.message.answer("👤 Sotmoqchi bo'lgan akkountingiz nomi/nima ekanini yozing:", reply_markup=cancel_kb(lang))
    await state.set_state(AccountSell.name)
    await cb.answer()

@dp.message(AccountSell.name)
async def acc_sell_name(msg: types.Message, state: FSMContext):
    lang = await get_user_lang(msg.from_user.id)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await state.update_data(acc_name=msg.text)
    await msg.answer("📸 Akkount rasmini (screenshot) yuboring yoki o'tkazib yuboring:", reply_markup=skip_cancel_kb(lang))
    await state.set_state(AccountSell.photo)

@dp.message(AccountSell.photo, F.photo)
async def acc_sell_photo(msg: types.Message, state: FSMContext):
    await state.update_data(acc_photo=msg.photo[-1].file_id)
    lang = await get_user_lang(msg.from_user.id)
    await msg.answer("💰 Narxini kiriting (so'mda):", reply_markup=cancel_kb(lang))
    await state.set_state(AccountSell.price)

@dp.message(AccountSell.photo)
async def acc_sell_no_photo(msg: types.Message, state: FSMContext):
    lang = await get_user_lang(msg.from_user.id)
    if msg.text == T(lang, "cancel") or msg.text == T(lang, "skip"):
        if msg.text == T(lang, "cancel"):
            await state.clear()
            await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
            return
        await state.update_data(acc_photo=None)
        await msg.answer("💰 Narxini kiriting (so'mda):", reply_markup=cancel_kb(lang))
        await state.set_state(AccountSell.price)
        return
    await state.update_data(acc_photo=None)
    await msg.answer("💰 Narxini kiriting (so'mda):", reply_markup=cancel_kb(lang))
    await state.set_state(AccountSell.price)

@dp.message(AccountSell.price)
async def acc_sell_price(msg: types.Message, state: FSMContext):
    lang = await get_user_lang(msg.from_user.id)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    txt = (msg.text or "").strip().replace(" ", "")
    if not txt.isdigit():
        await msg.answer("❌ Faqat raqam kiriting:")
        return
    await state.update_data(acc_price=int(txt))
    await msg.answer("📝 Akkount haqida qisqacha ma'lumot yozing (inventar, level va h.k.) yoki o'tkazib yuboring:", reply_markup=skip_cancel_kb(lang))
    await state.set_state(AccountSell.bio)

@dp.message(AccountSell.bio)
async def acc_sell_bio(msg: types.Message, state: FSMContext):
    uid  = msg.from_user.id
    lang = await get_user_lang(uid)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    bio = "" if msg.text == T(lang, "skip") else (msg.text or "")
    d = await state.get_data()
    doc = {
        "user_id": uid,
        "username": msg.from_user.username or "",
        "name": d.get("acc_name", ""),
        "photo_id": d.get("acc_photo"),
        "price": d.get("acc_price", 0),
        "bio": bio,
        "active": True,
        "created_at": now(),
    }
    res = await accounts_col.insert_one(doc)
    await state.clear()
    await msg.answer(
        f"✅ Akkount e'lon qilindi! *#{short_id(res.inserted_id)}*",
        reply_markup=main_kb(lang)
    )

@dp.callback_query(F.data == "acc_buy")
async def cb_acc_buy(cb: types.CallbackQuery):
    lang = await get_user_lang(cb.from_user.id)
    items = await active_accounts()
    if not items:
        await cb.answer("Hozircha sotuvdagi akkountlar yo'q.", show_alert=True)
        return
    await _send_account_page(cb, items, 0, lang=lang)
    await cb.answer()

async def _send_account_page(target, items, page, is_cb=True, lang="uz"):
    a = items[page]
    caption = (
        f"👤 *Akkount #{short_id(a['_id'])}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"[{page+1}/{len(items)}]\n\n"
        f"📦 *{esc_md(a.get('name',''))}*\n\n"
        f"📝 {esc_md(a.get('bio') or '—')}\n\n"
        f"💰 *{a.get('price',0):,} so'm*\n\n"
        f"📅 {a.get('created_at','')}\n━━━━━━━━━━━━━━━━━━━━"
    )
    b = InlineKeyboardBuilder()
    if page > 0:
        b.button(text="⬅️ Oldingi", callback_data=f"acc_p_{page-1}")
    if page < len(items) - 1:
        b.button(text="➡️ Keyingi", callback_data=f"acc_p_{page+1}")
    uname = a.get("username", "")
    if uname:
        b.button(text="💬 Murojaat", url=f"https://t.me/{uname}")
    b.adjust(2, 1)
    if is_cb:
        await _send_or_edit(target, a.get("photo_id"), caption, b.as_markup())
    else:
        if a.get("photo_id"):
            await target.answer_photo(a["photo_id"], caption=caption, reply_markup=b.as_markup())
        else:
            await target.answer(caption, reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("acc_p_"))
async def cb_acc_page(cb: types.CallbackQuery):
    lang = await get_user_lang(cb.from_user.id)
    page = int(cb.data[len("acc_p_"):])
    items = await active_accounts()
    if not items:
        await cb.answer("Hozircha sotuvdagi akkountlar yo'q.", show_alert=True)
        return
    page = max(0, min(page, len(items) - 1))
    await _send_account_page(cb, items, page, lang=lang)
    await cb.answer()


# ═══════════════════════════════════════════════════════
# PRO BO'LIMI (Trader ilova — admin yuklaydi, foydalanuvchi oladi)
# ═══════════════════════════════════════════════════════
pro_app_col = mdb["pro_app"]

class ProAppUpload(StatesGroup):
    file = State()

@dp.message(F.func(lambda msg: any(msg.text == T(l, "btn_pro_menu") for l in LANGS)))
async def cmd_pro_menu(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    lang = await get_user_lang(msg.from_user.id)
    doc = await pro_app_col.find_one({"_id": "current"})
    if not doc or not doc.get("file_id"):
        await msg.answer("💎 *Pro*\n\nHozircha ilova yuklanmagan. Tez orada qo'shiladi!")
        return
    b = InlineKeyboardBuilder()
    b.button(text="📥 Yuklab olish", callback_data="pro_get_file")
    b.adjust(1)
    await msg.answer(
        f"💎 *Pro — Trader ilovasi*\n\n{doc.get('caption','')}\n\n👇 Yuklab olish uchun bosing:",
        reply_markup=b.as_markup()
    )

@dp.callback_query(F.data == "pro_get_file")
async def cb_pro_get_file(cb: types.CallbackQuery):
    doc = await pro_app_col.find_one({"_id": "current"})
    if not doc or not doc.get("file_id"):
        await cb.answer("Ilova topilmadi.", show_alert=True)
        return
    await cb.message.answer_document(doc["file_id"], caption="💎 Pro — Trader ilovasi")
    await cb.answer()

# ── Admin: Pro ilovani yuklash/yangilash ──
@dp.callback_query(F.data == "adm_pro_upload")
async def adm_pro_upload(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await cb.message.answer("📎 Pro ilovaning faylini (.apk yoki boshqa) yuboring:", reply_markup=cancel_kb())
    await state.set_state(ProAppUpload.file)
    await cb.answer()

@dp.message(ProAppUpload.file, F.document)
async def adm_pro_file_got(msg: types.Message, state: FSMContext):
    lang = await get_user_lang(msg.from_user.id)
    await pro_app_col.update_one(
        {"_id": "current"},
        {"$set": {
            "file_id": msg.document.file_id,
            "caption": msg.caption or "",
            "uploaded_at": now(),
            "uploaded_by": msg.from_user.id,
        }},
        upsert=True
    )
    await state.clear()
    await msg.answer("✅ Pro ilova muvaffaqiyatli yuklandi/yangilandi!", reply_markup=main_kb(lang))

@dp.message(ProAppUpload.file)
async def adm_pro_file_wrong(msg: types.Message, state: FSMContext):
    lang = await get_user_lang(msg.from_user.id)
    if msg.text == T(lang, "cancel"):
        await state.clear()
        await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await msg.answer("❌ Iltimos, fayl (document) ko'rinishida yuboring:")


# ═══════════════════════════════════════════════════════
# WEB APP (Crash o'yin webapp'idan kelgan tugma bosishlari)
# ═══════════════════════════════════════════════════════
@dp.message(F.web_app_data)
async def on_web_app_data(msg: types.Message, state: FSMContext):
    try:
        data = json.loads(msg.web_app_data.data)
    except Exception:
        return
    action = data.get("action")
    lang = await get_user_lang(msg.from_user.id)
    if action == "open_sale_add":
        await cmd_sale_add(msg, state)
    elif action == "open_deposit":
        await cmd_deposit(msg, state)
    elif action == "open_buy":
        await cmd_buy(msg, state)
    elif action == "open_referral":
        await cmd_referral(msg, state)
    elif action == "open_withdraw":
        await msg.answer(
            "🚧 Pul yechish funksiyasi tez orada qo'shiladi." if lang == "uz"
            else "🚧 Withdraw feature coming soon."
        )


# ═══════════════════════════════════════════════════════
# POLLING + MAIN
# (Webhook o'rniga polling ishlatiladi — Render "Background Worker" yoki
#  "Web Service" bo'lishidan qat'iy nazar ishonchli ishlaydi, chunki
#  polling uchun tashqi/kiruvchi port ochish shart emas, faqat bot
#  Telegram serveriga o'zi so'rov yuborib turadi.)
# ═══════════════════════════════════════════════════════
WEB_PORT = int(os.getenv("PORT", 10000))


async def on_startup_polling():
    await init_indexes()
    await load_admin_roles()
    # Agar avval webhook o'rnatilgan bo'lsa, uni tozalaymiz (polling bilan
    # webhook bir vaqtda ishlay olmaydi)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logging.warning(f"Webhook o'chirishda xato (muhim emas): {e}")
    # AI Yordamchi: avval ulangan barcha shaxsiy akkauntlarni qayta ulaymiz
    try:
        await userbot_manager.restart_all()
    except Exception as e:
        logging.error(f"Userbot'larni qayta ulashda xato: {e}")
    logging.info("✅ Bot polling rejimida ishga tushdi")


def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

async def api_me(request):
    """GET /webapp/api/me?initData=... — foydalanuvchining REAL balansini qaytaradi (Mongo'dan)."""
    init_data = request.query.get("initData", "")
    tg_user = verify_webapp_initdata(init_data)
    if not tg_user:
        return _cors(web.json_response({"error": "unauthorized"}, status=401))
    uid = tg_user["id"]
    # Profilni (ism, username, rasm) har safar yangilab boramiz — Chat tizimi shu
    # ma'lumotlar orqali foydalanuvchini username bo'yicha topadi.
    await upsert_user_profile(tg_user)
    u = await get_user(uid)
    ref_count = await get_ref_count(uid)
    robux_rate = await get_robux_rate()
    return _cors(web.json_response({
        "balance": u.get("balance", 0),
        "total_deposited": u.get("total_deposited", 0),
        "joined": u.get("joined", ""),
        "ref_count": ref_count,
        "robux_balance": u.get("robux_balance", 0),
        "robux_rate_per_1000": robux_rate * 1000,
    }))

# ═══════════════════════════════════════════════════════
# CHAT TIZIMI (Shaxsiy + Global) — Web App API
# ═══════════════════════════════════════════════════════
async def _upload_chat_media(uid, media_type, media_b64):
    """Frontend'dan kelgan base64 media'ni Telegram serverlariga (bot orqali,
    yuboruvchining shaxsiy chatiga) yuklab, hammabop file_id/URL qaytaradi."""
    if not media_b64:
        return None, None
    try:
        if "," in media_b64:
            media_b64 = media_b64.split(",", 1)[1]
        media_bytes = base64.b64decode(media_b64)
    except Exception:
        return None, None
    try:
        if media_type == "video":
            sent = await bot.send_video(chat_id=uid, video=types.BufferedInputFile(media_bytes, filename="chat_video.mp4"))
            file_id = sent.video.file_id
        elif media_type == "voice":
            sent = await bot.send_voice(chat_id=uid, voice=types.BufferedInputFile(media_bytes, filename="chat_voice.ogg"))
            file_id = sent.voice.file_id
        else:
            sent = await bot.send_photo(chat_id=uid, photo=types.BufferedInputFile(media_bytes, filename="chat_photo.jpg"))
            file_id = sent.photo[-1].file_id
    except Exception:
        return None, None
    return file_id, f"/webapp/api/photo/{file_id}"

async def api_chat_global(request):
    """GET /webapp/api/chat/global?initData=...&after=<ts_ms> — global chat xabarlari."""
    tg_user = verify_webapp_initdata(request.query.get("initData", ""))
    if not tg_user:
        return _cors(web.json_response({"error": "unauthorized"}, status=401))
    try:
        after = int(request.query.get("after", 0) or 0)
    except Exception:
        after = 0
    if after:
        docs = await chat_global_col.find({"ts": {"$gt": after}}).sort("ts", 1).to_list(length=200)
    else:
        docs = await chat_global_col.find({}).sort("ts", -1).to_list(length=50)
        docs.reverse()
    messages = [{
        "user_id": d.get("user_id"), "name": d.get("name", ""), "username": d.get("username", ""),
        "photo_url": d.get("photo_url", ""), "text": d.get("text", ""),
        "media_type": d.get("media_type"), "media_url": d.get("media_url"),
        "reply_to": d.get("reply_to"), "ts": d.get("ts", 0),
    } for d in docs]
    return _cors(web.json_response({"messages": messages}))

async def api_chat_global_send(request):
    """POST /webapp/api/chat/global/send {initData, text, media_type, media_base64}"""
    try:
        body = await request.json()
    except Exception:
        return _cors(web.json_response({"error": "bad_request"}, status=400))
    tg_user = verify_webapp_initdata(body.get("initData", ""))
    if not tg_user:
        return _cors(web.json_response({"error": "unauthorized"}, status=401))
    uid = tg_user["id"]
    await upsert_user_profile(tg_user)
    text = (body.get("text") or "").strip()[:2000]
    media_type = body.get("media_type")
    media_b64 = body.get("media_base64")
    media_url = None
    if media_type == "sticker" and media_b64:
        media_url = str(media_b64)[:16]
    elif media_type and media_b64:
        _, media_url = await _upload_chat_media(uid, media_type, media_b64)
        if not media_url:
            return _cors(web.json_response({"error": "media_upload_failed"}, status=500))
    if not text and not media_url:
        return _cors(web.json_response({"error": "empty_message"}, status=400))
    doc = {
        "user_id": uid,
        "name": display_name(tg_user),
        "username": tg_user.get("username", "") or "",
        "photo_url": tg_user.get("photo_url", "") or "",
        "text": text,
        "media_type": media_type if media_url else None,
        "media_url": media_url,
        "reply_to": _sanitize_reply_to(body.get("reply_to")),
        "ts": int(time.time() * 1000),
    }
    await chat_global_col.insert_one(doc)
    doc.pop("_id", None)
    return _cors(web.json_response({"message": doc}))

async def api_chat_contacts(request):
    """GET /webapp/api/chat/contacts?initData=... — shaxsiy chat kontaktlar ro'yxati."""
    tg_user = verify_webapp_initdata(request.query.get("initData", ""))
    if not tg_user:
        return _cors(web.json_response({"error": "unauthorized"}, status=401))
    uid = tg_user["id"]
    await upsert_user_profile(tg_user)
    contact_docs = await chat_contacts_col.find({"owner_id": uid}).to_list(length=500)
    result = []
    for c in contact_docs:
        peer_id = c["peer_id"]
        peer = await get_user(peer_id)
        if not peer:
            continue
        last = await chat_private_col.find({
            "$or": [{"from_id": uid, "to_id": peer_id}, {"from_id": peer_id, "to_id": uid}]
        }).sort("ts", -1).limit(1).to_list(length=1)
        last_text, last_ts, last_media = "", 0, False
        if last:
            last_text = last[0].get("text", "")
            last_ts = last[0].get("ts", 0)
            last_media = bool(last[0].get("media_type"))
        result.append({
            "user_id": peer_id,
            "name": display_name(peer),
            "username": peer.get("username", ""),
            "photo_url": peer.get("photo_url", ""),
            "last_text": last_text, "last_ts": last_ts, "last_media": last_media,
        })
    result.sort(key=lambda x: x["last_ts"], reverse=True)
    return _cors(web.json_response({"contacts": result}))

async def api_chat_contacts_add(request):
    """POST /webapp/api/chat/contacts/add {initData, username} — username orqali
    foydalanuvchi qidirib, ikki tomonlama shaxsiy chatga qo'shadi."""
    try:
        body = await request.json()
    except Exception:
        return _cors(web.json_response({"error": "bad_request"}, status=400))
    tg_user = verify_webapp_initdata(body.get("initData", ""))
    if not tg_user:
        return _cors(web.json_response({"error": "unauthorized"}, status=401))
    uid = tg_user["id"]
    await upsert_user_profile(tg_user)
    uname = (body.get("username") or "").strip()
    if not uname:
        return _cors(web.json_response({"error": "bad_username"}, status=400))
    peer = await find_user_by_username(uname)
    if not peer:
        return _cors(web.json_response({"error": "not_found"}, status=404))
    peer_id = peer["user_id"]
    if peer_id == uid:
        return _cors(web.json_response({"error": "self"}, status=400))
    await ensure_chat_contact(uid, peer_id)
    await ensure_chat_contact(peer_id, uid)
    return _cors(web.json_response({"contact": {
        "user_id": peer_id,
        "name": display_name(peer),
        "username": peer.get("username", ""),
        "photo_url": peer.get("photo_url", ""),
        "last_text": "", "last_ts": 0,
    }}))

async def api_chat_peer(request):
    """GET /webapp/api/chat/peer?initData=...&peer_id=... — bot orqali kelgan
    '👀 Ko'rish' tugmasi bosilganda, Web App o'sha suhbatni to'g'ridan-to'g'ri
    ochishi uchun peer profilini qaytaradi va kontaktni ikki tomonlama qo'shadi."""
    tg_user = verify_webapp_initdata(request.query.get("initData", ""))
    if not tg_user:
        return _cors(web.json_response({"error": "unauthorized"}, status=401))
    uid = tg_user["id"]
    await upsert_user_profile(tg_user)
    try:
        peer_id = int(request.query.get("peer_id", 0) or 0)
    except Exception:
        return _cors(web.json_response({"error": "bad_peer"}, status=400))
    peer = await get_user(peer_id)
    if not peer:
        return _cors(web.json_response({"error": "not_found"}, status=404))
    await ensure_chat_contact(uid, peer_id)
    await ensure_chat_contact(peer_id, uid)
    return _cors(web.json_response({"contact": {
        "user_id": peer_id,
        "name": display_name(peer),
        "username": peer.get("username", ""),
        "photo_url": peer.get("photo_url", ""),
        "last_text": "", "last_ts": 0,
    }}))

async def api_chat_private(request):
    """GET /webapp/api/chat/private?initData=...&peer_id=...&after=<ts_ms>"""
    tg_user = verify_webapp_initdata(request.query.get("initData", ""))
    if not tg_user:
        return _cors(web.json_response({"error": "unauthorized"}, status=401))
    uid = tg_user["id"]
    try:
        peer_id = int(request.query.get("peer_id", 0) or 0)
    except Exception:
        return _cors(web.json_response({"error": "bad_peer"}, status=400))
    try:
        after = int(request.query.get("after", 0) or 0)
    except Exception:
        after = 0
    q = {"$or": [{"from_id": uid, "to_id": peer_id}, {"from_id": peer_id, "to_id": uid}]}
    if after:
        q["ts"] = {"$gt": after}
        docs = await chat_private_col.find(q).sort("ts", 1).to_list(length=200)
    else:
        docs = await chat_private_col.find(q).sort("ts", -1).to_list(length=50)
        docs.reverse()
    messages = [{
        "user_id": d.get("from_id"), "name": d.get("name", ""), "text": d.get("text", ""),
        "media_type": d.get("media_type"), "media_url": d.get("media_url"),
        "reply_to": d.get("reply_to"), "ts": d.get("ts", 0),
    } for d in docs]
    return _cors(web.json_response({"messages": messages}))

def _sanitize_reply_to(raw):
    """Frontend'dan kelgan reply_to ma'lumotini xavfsiz, qisqartirilgan holda saqlaydi."""
    if not isinstance(raw, dict):
        return None
    try:
        ref_ts = int(raw.get("ts", 0) or 0)
    except Exception:
        ref_ts = 0
    if not ref_ts:
        return None
    return {
        "ts": ref_ts,
        "name": str(raw.get("name") or "Foydalanuvchi")[:80],
        "text": str(raw.get("text") or "")[:200],
        "media_type": raw.get("media_type") if raw.get("media_type") in ("photo", "video", "voice", "sticker") else None,
    }

async def _notify_private_message(peer_id: int, sender_tg_user: dict, text: str, media_type):
    """Shaxsiy chatda kimdir yozganda, qabul qiluvchiga bot orqali xabar yuboradi:
    kim yozdi, soati va Web App'dagi o'sha suhbatni to'g'ridan-to'g'ri ochadigan
    '👀 Ko'rish' tugmasi bilan."""
    try:
        sender_name = display_name(sender_tg_user)
        sender_uname = sender_tg_user.get("username", "") or ""
        time_str = (datetime.utcnow() + timedelta(hours=5)).strftime("%H:%M")

        if media_type == "sticker":
            preview = "😊 Stiker yubordi"
        elif media_type == "photo":
            preview = "📷 Rasm yubordi"
        elif media_type == "video":
            preview = "🎬 Video yubordi"
        elif media_type == "voice":
            preview = "🎤 Ovozli xabar yubordi"
        else:
            snippet = (text or "").strip()
            if len(snippet) > 120:
                snippet = snippet[:120] + "…"
            preview = f"_{esc_md(snippet)}_" if snippet else "Xabar yubordi"

        uname_line = f" (@{esc_md(sender_uname)})" if sender_uname else ""
        msg_text = (
            f"✉️ *{esc_md(sender_name)}*{uname_line} sizga yozdi\n"
            f"🕐 *{time_str}*\n\n"
            f"{preview}"
        )

        kb = InlineKeyboardBuilder()
        if WEBAPP_URL:
            deep_url = f"{WEBAPP_URL}?open_chat={sender_tg_user['id']}"
            kb.button(text="👀 Ko'rish", web_app=WebAppInfo(url=deep_url))

        await bot.send_message(peer_id, msg_text, reply_markup=kb.as_markup() if WEBAPP_URL else None)
    except Exception as e:
        logging.warning(f"Shaxsiy chat bildirishnomasi yuborilmadi ({peer_id}): {e}")

async def api_chat_private_send(request):
    """POST /webapp/api/chat/private/send {initData, peer_id, text, media_type, media_base64, reply_to}"""
    try:
        body = await request.json()
    except Exception:
        return _cors(web.json_response({"error": "bad_request"}, status=400))
    tg_user = verify_webapp_initdata(body.get("initData", ""))
    if not tg_user:
        return _cors(web.json_response({"error": "unauthorized"}, status=401))
    uid = tg_user["id"]
    await upsert_user_profile(tg_user)
    try:
        peer_id = int(body.get("peer_id", 0) or 0)
    except Exception:
        return _cors(web.json_response({"error": "bad_peer"}, status=400))
    peer = await get_user(peer_id)
    if not peer:
        return _cors(web.json_response({"error": "peer_not_found"}, status=404))
    text = (body.get("text") or "").strip()[:2000]
    media_type = body.get("media_type")
    media_b64 = body.get("media_base64")
    media_url = None
    if media_type == "sticker" and media_b64:
        # Stiker — haqiqiy fayl emas, shunchaki emoji/belgi, yuklashning hojati yo'q.
        media_url = str(media_b64)[:16]
    elif media_type and media_b64:
        _, media_url = await _upload_chat_media(uid, media_type, media_b64)
        if not media_url:
            return _cors(web.json_response({"error": "media_upload_failed"}, status=500))
    if not text and not media_url:
        return _cors(web.json_response({"error": "empty_message"}, status=400))
    await ensure_chat_contact(uid, peer_id)
    await ensure_chat_contact(peer_id, uid)
    reply_to = _sanitize_reply_to(body.get("reply_to"))
    doc = {
        "from_id": uid, "to_id": peer_id,
        "name": display_name(tg_user),
        "text": text,
        "media_type": media_type if media_url else None,
        "media_url": media_url,
        "reply_to": reply_to,
        "ts": int(time.time() * 1000),
    }
    await chat_private_col.insert_one(doc)
    doc.pop("_id", None)
    asyncio.create_task(_notify_private_message(peer_id, tg_user, text, doc["media_type"]))
    return _cors(web.json_response({"message": {**doc, "user_id": doc["from_id"]}}))

async def api_crash_bet(request):
    """POST /webapp/api/bet {initData, amount} — stavkani serverda balansdan yechadi."""
    try:
        body = await request.json()
    except Exception:
        return _cors(web.json_response({"error": "bad_request"}, status=400))
    tg_user = verify_webapp_initdata(body.get("initData", ""))
    if not tg_user:
        return _cors(web.json_response({"error": "unauthorized"}, status=401))
    uid = tg_user["id"]
    try:
        amount = int(body.get("amount", 0))
    except Exception:
        return _cors(web.json_response({"error": "bad_amount"}, status=400))
    if amount < 1000 or amount > 200000:
        return _cors(web.json_response({"error": "invalid_amount"}, status=400))
    bal = await get_balance(uid)
    if bal < amount:
        return _cors(web.json_response({"error": "insufficient_balance", "balance": bal}, status=400))
    await sub_balance(uid, amount)
    new_bal = await get_balance(uid)
    return _cors(web.json_response({"balance": new_bal}))

async def api_crash_cashout(request):
    """POST /webapp/api/cashout {initData, amount} — yutuqni serverda balansga qo'shadi."""
    try:
        body = await request.json()
    except Exception:
        return _cors(web.json_response({"error": "bad_request"}, status=400))
    tg_user = verify_webapp_initdata(body.get("initData", ""))
    if not tg_user:
        return _cors(web.json_response({"error": "unauthorized"}, status=401))
    uid = tg_user["id"]
    try:
        amount = int(body.get("amount", 0))
    except Exception:
        return _cors(web.json_response({"error": "bad_amount"}, status=400))
    if amount <= 0:
        return _cors(web.json_response({"error": "invalid_amount"}, status=400))
    await add_win_balance(uid, amount)
    new_bal = await get_balance(uid)
    return _cors(web.json_response({"balance": new_bal}))

async def api_exchange(request):
    """POST /webapp/api/exchange {initData, amount} — balansdan (so'm) Robux'ga ayirboshlaydi."""
    try:
        body = await request.json()
    except Exception:
        return _cors(web.json_response({"error": "bad_request"}, status=400))
    tg_user = verify_webapp_initdata(body.get("initData", ""))
    if not tg_user:
        return _cors(web.json_response({"error": "unauthorized"}, status=401))
    uid = tg_user["id"]
    try:
        amount = int(body.get("amount", 0))
    except Exception:
        return _cors(web.json_response({"error": "bad_amount"}, status=400))
    if amount < 1000:
        return _cors(web.json_response({"error": "invalid_amount"}, status=400))
    bal = await get_balance(uid)
    if bal < amount:
        return _cors(web.json_response({"error": "insufficient_balance", "balance": bal}, status=400))
    rate = await get_robux_rate()
    robux_gained = round(amount * rate, 4)
    await sub_balance(uid, amount)
    await add_robux(uid, robux_gained)
    new_bal = await get_balance(uid)
    new_robux = await get_robux_balance(uid)
    return _cors(web.json_response({
        "balance": new_bal,
        "robux_balance": new_robux,
        "robux_gained": robux_gained,
    }))

async def api_sales(request):
    """GET /webapp/api/sales — barcha faol e'lonlarni o'yin bo'yicha guruhlab qaytaradi."""
    items = await active_sales()
    grouped = {}
    for it in items:
        game_key = it.get("game") or "boshqa"
        grouped.setdefault(game_key, []).append({
            "id": str(it["_id"]),
            "name": it.get("name", ""),
            "price": it.get("price", 0),
            "currency": it.get("currency", "so'm"),
            "photo_url": f"/webapp/api/photo/{it['photo_id']}" if it.get("photo_id") else None,
        })
    sections = []
    for key, label in GAME_CATEGORIES:
        sections.append({"key": key, "label": label, "items": grouped.get(key, [])})
    if grouped.get("boshqa"):
        sections.append({"key": "boshqa", "label": "🗂️ Boshqa", "items": grouped["boshqa"]})
    return _cors(web.json_response({"sections": sections}))

async def api_photo(request):
    """GET /webapp/api/photo/{file_id} — Telegram fayl serverdan olib, brauzerga uzatadi (tokenni oshkor qilmasdan)."""
    file_id = request.match_info.get("file_id", "")
    try:
        file = await bot.get_file(file_id)
        url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return web.Response(status=404)
                data = await resp.read()
                ctype = resp.headers.get("Content-Type", "image/jpeg")
        return web.Response(body=data, content_type=ctype)
    except Exception:
        return web.Response(status=404)

async def api_sale_add(request):
    """POST /webapp/api/sale/add {initData, game, price, photo_base64} —
    Web App ichidan to'g'ridan-to'g'ri savdo e'loni yaratadi (chatga chiqmasdan)."""
    try:
        body = await request.json()
    except Exception:
        return _cors(web.json_response({"error": "bad_request"}, status=400))
    tg_user = verify_webapp_initdata(body.get("initData", ""))
    if not tg_user:
        return _cors(web.json_response({"error": "unauthorized"}, status=401))
    uid = tg_user["id"]
    uname = tg_user.get("username", "")
    game = body.get("game", "")
    photo_b64 = body.get("photo_base64", "")
    try:
        price = int(body.get("price", 0))
    except Exception:
        return _cors(web.json_response({"error": "bad_price"}, status=400))

    if game not in GAME_LABELS:
        return _cors(web.json_response({"error": "bad_game"}, status=400))
    if price <= 0:
        return _cors(web.json_response({"error": "bad_price"}, status=400))
    if not photo_b64:
        return _cors(web.json_response({"error": "no_photo"}, status=400))

    try:
        if "," in photo_b64:
            photo_b64 = photo_b64.split(",", 1)[1]
        photo_bytes = base64.b64decode(photo_b64)
    except Exception:
        return _cors(web.json_response({"error": "bad_photo"}, status=400))

    try:
        sent = await bot.send_photo(
            chat_id=uid,
            photo=types.BufferedInputFile(photo_bytes, filename="sale.jpg"),
            caption="🛍️ Web App orqali qo'shilgan savdo e'loni"
        )
        file_id = sent.photo[-1].file_id
    except Exception:
        return _cors(web.json_response({"error": "photo_upload_failed"}, status=500))

    lang = await get_user_lang(uid)
    game_label = GAME_LABELS.get(game, game)
    sid = await add_sale(uid, uname, "", game_label, "", file_id, "so'm", price, lang=lang, game=game)

    return _cors(web.json_response({
        "success": True,
        "item": {
            "id": str(sid),
            "name": game_label,
            "price": price,
            "currency": "so'm",
            "photo_url": f"/webapp/api/photo/{file_id}",
            "game": game,
            "game_label": game_label,
        }
    }))

async def api_options(request):
    return _cors(web.Response())


async def _run_health_server():
    """Render 'Web Service' turi uchun port ochib turadigan yengil server.
    Agar 'Background Worker' bo'lsa ham, bu server zarar keltirmaydi."""
    app = web.Application(client_max_size=10 * 1024 * 1024)

    async def health(request):
        return web.Response(text="OK - bot ishlayapti (polling)")

    app.router.add_get("/", health)

    # 🎮 Crash o'yin Web App uchun REAL balans API (statikdan OLDIN ro'yxatdan o'tkaziladi)
    app.router.add_get("/webapp/api/me", api_me)
    app.router.add_post("/webapp/api/bet", api_crash_bet)
    app.router.add_post("/webapp/api/cashout", api_crash_cashout)
    app.router.add_post("/webapp/api/exchange", api_exchange)
    app.router.add_get("/webapp/api/sales", api_sales)
    app.router.add_post("/webapp/api/sale/add", api_sale_add)
    app.router.add_get("/webapp/api/photo/{file_id}", api_photo)

    # 💬 Chat tizimi (Shaxsiy + Global) uchun API
    app.router.add_get("/webapp/api/chat/global", api_chat_global)
    app.router.add_post("/webapp/api/chat/global/send", api_chat_global_send)
    app.router.add_get("/webapp/api/chat/contacts", api_chat_contacts)
    app.router.add_post("/webapp/api/chat/contacts/add", api_chat_contacts_add)
    app.router.add_get("/webapp/api/chat/private", api_chat_private)
    app.router.add_post("/webapp/api/chat/private/send", api_chat_private_send)
    app.router.add_get("/webapp/api/chat/peer", api_chat_peer)

    app.router.add_route("OPTIONS", "/webapp/api/{tail:.*}", api_options)

    # 🏆 Yutuqli o'yin uchun Web App fayllarini xizmat qilish (webapp/index.html)
    webapp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp")
    if os.path.isdir(webapp_dir):
        app.router.add_static("/webapp/", webapp_dir, show_index=False)
        logging.info(f"🏆 Web App statik fayllari ulandi: {webapp_dir}")
    else:
        logging.warning(f"⚠️ 'webapp' papkasi topilmadi: {webapp_dir}")

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=WEB_PORT)
    await site.start()
    logging.info(f"🌐 Health-check server {WEB_PORT} portda ishga tushdi")


async def main_async():
    await on_startup_polling()
    await _run_health_server()
    asyncio.create_task(broadcast_scheduler_loop())
    await dp.start_polling(bot)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
