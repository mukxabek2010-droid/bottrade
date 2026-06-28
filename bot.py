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
# Majburiy obuna — 3 ta kanal
REQUIRED_CHANNELS = ["@bulldrop_n1", "@uzbekroblox", "@trade_chanel_uz"]
TRADE_CHANNEL     = "@trade_chanel_uz"   # e'lonlar yuboriladigan kanal
CARD_NUMBER       = os.getenv("CARD_NUMBER", "5614682091344749")   # tire YO'Q
CARD_OWNER        = os.getenv("CARD_OWNER", "Nurboyev.N")
CHAT_LINK         = os.getenv("CHAT_LINK", "https://t.me/roblox_chat_veko")

# 2 ta admin ID
ADMIN_IDS = {8325726426, 8667862086}

def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

# Birinchi admin (xabarnomalar uchun)
ADMIN_ID = 8667862086

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
autoxabar_db   = mdb["autoxabar"]
online_traders = mdb["online_traders"]   # yangi kolleksiya
trade_cart     = mdb["trade_cart"]       # savat — tradelar
sale_cart      = mdb["sale_cart"]        # savat — sotuvlar

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

async def upsert_user(uid, uname):
    upd = {
        "$set": {"username": uname, "last_seen": now()},
        "$setOnInsert": {"user_id": uid, "balance": 0, "total_deposited": 0, "joined": now()}
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
async def add_order(uid, uname, nick, robux, price, mood=""):
    r = await orders.insert_one({
        "user_id": uid, "username": uname, "roblox_nick": nick,
        "robux_amount": robux, "price_sum": price, "mood": mood,
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

# trades
async def add_trade(uid, uname, nick, name, bio, photo_id):
    r = await trades.insert_one({
        "user_id": uid, "username": uname, "roblox_nick": nick,
        "name": name, "bio": bio, "photo_id": photo_id,
        "status": "active", "created_at": now()
    })
    return r.inserted_id

async def get_trade(tid):
    return await trades.find_one({"_id": ObjectId(str(tid))})

async def active_trades():
    return [t async for t in trades.find({"status": "active"}).sort("_id", -1)]

async def my_trades(uid):
    return [t async for t in trades.find({"user_id": uid, "status": "active"}).sort("_id", -1)]

async def edit_trade(tid, name, bio):
    await trades.update_one({"_id": ObjectId(str(tid))}, {"$set": {"name": name, "bio": bio}})

async def delete_trade(tid):
    await trades.update_one({"_id": ObjectId(str(tid))}, {"$set": {"status": "deleted"}})

# sales
async def add_sale(uid, uname, nick, name, bio, photo_id, currency, price):
    r = await sales.insert_one({
        "user_id": uid, "username": uname, "roblox_nick": nick,
        "name": name, "bio": bio, "photo_id": photo_id, "currency": currency,
        "price": price, "status": "active", "created_at": now()
    })
    return r.inserted_id

async def get_sale(sid):
    return await sales.find_one({"_id": ObjectId(str(sid))})

async def active_sales():
    return [s async for s in sales.find({"status": "active"}).sort("_id", -1)]

async def my_sales(uid):
    return [s async for s in sales.find({"user_id": uid, "status": "active"}).sort("_id", -1)]

async def edit_sale(sid, name, price):
    await sales.update_one({"_id": ObjectId(str(sid))}, {"$set": {"name": name, "price": price}})

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
    (240, 42000), (280, 49000), (320, 56000), (360, 63000), (400, 65000),
    (440, 72000), (480, 79000), (520, 86000), (560, 93000), (700, 100000),
    (740, 107000), (780, 114000), (820, 121000), (860, 128000),
    (1000, 132000), (1500, 197000), (2000, 265000),
]

def price_for(robux):
    for r, p in ROBUX_PRICES:
        if r == robux:
            return p
    return None

DEPOSIT_OPTIONS = [5000, 10000, 15000, 20000, 30000, 50000, 100000]

# ═══════════════════════════════════════════════════════
# STATES
# ═══════════════════════════════════════════════════════
class Dep(StatesGroup):
    custom_amount = State()
    check_photo   = State()

class TradeAdd(StatesGroup):
    name  = State()
    photo = State()
    bio   = State()

class TradeEdit(StatesGroup):
    name = State()
    bio  = State()

class BuyFlow(StatesGroup):
    nick = State()
    mood = State()

class SaleAdd(StatesGroup):
    name     = State()
    photo    = State()
    bio      = State()
    currency = State()
    price    = State()

class SaleEdit(StatesGroup):
    name  = State()
    price = State()

class Broadcast(StatesGroup):
    photo = State()
    text  = State()

class AdminCmd(StatesGroup):
    add_balance = State()

class ContactAdmin(StatesGroup):
    photo   = State()
    message = State()

class SuggestBot(StatesGroup):
    photo   = State()
    message = State()

class AdFlow(StatesGroup):
    photo = State()
    bio   = State()

# Online trader states
class OnlineTraderAdd(StatesGroup):
    photo = State()
    nick  = State()
    bio   = State()

class OnlineTraderEdit(StatesGroup):
    nick  = State()
    bio   = State()

# ═══════════════════════════════════════════════════════
# BOT + DP
# ═══════════════════════════════════════════════════════
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp  = Dispatcher(storage=MemoryStorage())

# ═══════════════════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════════════════
CHANNEL_LABELS = {
    "@bulldrop_n1":      "1️⃣ @bulldrop_n1 kanalga obuna bo'lish",
    "@uzbekroblox":      "2️⃣ @uzbekroblox kanalga obuna bo'lish",
    "@trade_chanel_uz":  "3️⃣ @trade_chanel_uz kanalga obuna bo'lish",
}

def sub_kb(missing_channels=None):
    if missing_channels is None:
        missing_channels = REQUIRED_CHANNELS
    b = InlineKeyboardBuilder()
    for ch in missing_channels:
        label = CHANNEL_LABELS.get(ch, f"📢 {ch} kanalga obuna bo'lish")
        b.button(text=label, url=f"https://t.me/{ch.lstrip('@')}")
    b.button(text="✅ Obunani tasdiqlash", callback_data="check_sub")
    b.adjust(1)
    return b.as_markup()

def main_kb():
    b = ReplyKeyboardBuilder()
    b.button(text="🛒 Robux sotib olish")
    b.button(text="👤 Profil")
    b.button(text="💰 Hisob to'ldirish")
    b.button(text="🔄 Tradelar")
    b.button(text="📊 Sotuvlar")
    b.button(text="➕ Trade qo'shish")
    b.button(text="➕ Sotish qo'shish")
    b.button(text="🌐 Online Traderlar")
    b.button(text="🛒 Savat")
    b.button(text="💬 Chat")
    b.button(text="📜 Shartnoma qilish")
    b.button(text="📣 Reklama qilish")
    b.button(text="🛡 Adminlik xizmati")
    b.button(text="💡 Taklif berish")
    b.button(text="🔍 Qidiruv")
    b.adjust(2, 2, 2, 2, 2, 1, 2, 1)
    return b.as_markup(resize_keyboard=True)

def cancel_kb():
    b = ReplyKeyboardBuilder()
    b.button(text="❌ Bekor qilish")
    return b.as_markup(resize_keyboard=True)

def skip_cancel_kb():
    b = ReplyKeyboardBuilder()
    b.button(text="⏭ O'tkazib yuborish")
    b.button(text="❌ Bekor qilish")
    b.adjust(2)
    return b.as_markup(resize_keyboard=True)

# ═══════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════
async def not_subscribed_channels(uid: int) -> list:
    """Obuna bo'lmagan kanallar ro'yxatini qaytaradi. Bo'sh ro'yxat = hammasiga obuna."""
    missing = []
    for ch in REQUIRED_CHANNELS:
        try:
            m = await bot.get_chat_member(chat_id=ch, user_id=uid)
            if m.status in ["left", "kicked", "banned"]:
                missing.append(ch)
        except Exception as e:
            logging.error(f"Sub check xato ({ch}): {e}")
            # Bot kanalga admin qilib qo'shilmagan yoki kanal topilmadi —
            # xavfsizlik uchun obuna bo'lmagan deb hisoblaymiz va admin loglarda ko'radi
            missing.append(ch)
    return missing

async def is_sub(uid: int) -> bool:
    missing = await not_subscribed_channels(uid)
    return len(missing) == 0

async def check_access(msg: types.Message, state: FSMContext) -> bool:
    uid = msg.from_user.id
    missing = await not_subscribed_channels(uid)
    if missing:
        await msg.answer(
            "❌ Botdan foydalanish uchun avval barcha kanallarga obuna bo'ling!",
            reply_markup=sub_kb(missing)
        )
        return False
    return True

async def _send_or_edit(cb: types.CallbackQuery, photo_id, text, markup):
    try:
        if photo_id:
            if cb.message.photo:
                await cb.message.edit_caption(caption=text, reply_markup=markup)
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
async def post_trade_to_channel(uname: str, item_name: str, bio: str, photo_id=None):
    caption = (
        "🔄 *YANGI TRADE E'LON*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"1️⃣ *Foydalanuvchi:* @{esc_md(uname)}\n\n"
        f"2️⃣ *Buyum nomi:*\n{esc_md(item_name)}\n\n"
        f"3️⃣ *Bio:*\n{esc_md(bio or '—')}\n\n"
        "4️⃣ 🔄 *Trade*\n\n"
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
        logging.error(f"Kanalga trade yuborishda xato: {e}")

async def post_sale_to_channel(uname: str, item_name: str, bio: str, price, currency: str, photo_id=None):
    caption = (
        "🏷 *YANGI SOTUV E'LON*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"1️⃣ *Foydalanuvchi:* @{esc_md(uname)}\n\n"
        f"2️⃣ *Buyum nomi:*\n{esc_md(item_name)}\n\n"
        f"3️⃣ *Bio:*\n{esc_md(bio or '—')}\n\n"
        f"4️⃣ 🏷 *Sotiladi* — {int(price):,} {esc_md(currency)}\n\n"
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
# /START + OBUNA
# ═══════════════════════════════════════════════════════
@dp.message(Command("start"))
async def cmd_start(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    missing = await not_subscribed_channels(uid)
    if missing:
        await msg.answer(
            "👋 Salom! Botdan foydalanish uchun avval quyidagi kanallarga obuna bo'ling!",
            reply_markup=sub_kb(missing)
        )
        return
    await upsert_user(uid, msg.from_user.username or "user")
    await msg.answer(
        f"🌟 *Assalomu alaykum, {msg.from_user.first_name}!*\n\n"
        f"🤖 Bu bot orqali siz:\n"
        f"🛒 Robux sotib olishingiz,\n"
        f"📊 O'z buyumlaringizni sotishingiz,\n"
        f"🔄 Boshqa foydalanuvchilar bilan trade qilishingiz,\n"
        f"📜 Admin bilan shartnoma asosida ishlashingiz mumkin.\n\n"
        f"👇 Quyidagi menyudan foydalaning:",
        reply_markup=main_kb()
    )

@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    missing = await not_subscribed_channels(uid)
    if missing:
        await cb.answer("❌ Hali barcha kanallarga obuna bo'lmagansiz!", show_alert=True)
        try:
            await cb.message.edit_reply_markup(reply_markup=sub_kb(missing))
        except Exception:
            pass
        return
    try:
        await cb.message.delete()
    except Exception:
        pass
    await upsert_user(uid, cb.from_user.username or "user")
    await cb.message.answer("✅ Xush kelibsiz!", reply_markup=main_kb())
    await cb.answer()

# ═══════════════════════════════════════════════════════
# PROFIL
# ═══════════════════════════════════════════════════════
@dp.message(F.text == "👤 Profil")
async def cmd_profile(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid = msg.from_user.id
    u   = await get_user(uid)
    tr  = await my_trades(uid)
    sl  = await my_sales(uid)
    b   = InlineKeyboardBuilder()
    if tr:
        b.button(text=f"🔄 Mening tradelarim ({len(tr)})", callback_data="my_trades_0")
    if sl:
        b.button(text=f"🛍 Mening sotuvlarim ({len(sl)})", callback_data="my_sales_0")
    b.adjust(1)
    await msg.answer(
        f"👤 *Profilingiz*\n\n"
        f"🆔 ID: `{uid}`\n"
        f"💰 Balans: *{u.get('balance', 0):,} so'm*\n"
        f"📈 Jami kiritilgan: *{u.get('total_deposited', 0):,} so'm*\n"
        f"📅 Ro'yxat: {u.get('joined', '-')}\n\n"
        f"🔄 Faol tradelarim: {len(tr)}\n"
        f"🛍 Faol sotuvlarim: {len(sl)}",
        reply_markup=b.as_markup() if (tr or sl) else None
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
@dp.message(F.text == "💰 Hisob to'ldirish")
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
    missing = await not_subscribed_channels(cb.from_user.id)
    if missing:
        await cb.answer("❌ Avval barcha kanallarga obuna bo'ling!", show_alert=True)
        return
    if cb.data == "damt_custom":
        await cb.message.answer("✏️ Miqdorni yozing (so'mda, min 1000):", reply_markup=cancel_kb())
        await state.set_state(Dep.custom_amount)
        await cb.answer()
        return
    amount = int(cb.data.split("_")[1])
    await state.update_data(dep_amount=amount)
    await _show_card(cb.message, amount)
    await cb.answer()

@dp.message(Dep.custom_amount)
async def dep_custom(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
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
    # Karta raqamini formatlash — tire yo'q, bo'sh joy bilan
    card_display = CARD_NUMBER.replace("-", "").replace(" ", "")
    # 4ta raqam guruhlab ko'rsatish
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
    d = await state.get_data()
    if not d.get("dep_amount"):
        await cb.answer("❌ Xatolik! Qaytadan boshlang.", show_alert=True)
        await state.clear()
        return
    await cb.message.answer("📸 To'lov chekining rasmini yuboring (screenshot):", reply_markup=cancel_kb())
    await state.set_state(Dep.check_photo)
    await cb.answer()

@dp.callback_query(F.data == "dep_cancel")
async def cb_dep_cancel(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.message.answer("❌ Bekor qilindi.", reply_markup=main_kb())
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
    await msg.answer(f"✅ Chek yuborildi! Admin tasdiqlashini kuting.\n📋 To'lov #{short_id(did)}", reply_markup=main_kb())

@dp.message(Dep.check_photo)
async def dep_not_photo(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor qilindi.", reply_markup=main_kb())
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
    try:
        await bot.send_message(dep["user_id"], f"✅ To'lovingiz tasdiqlandi!\n💰 *{dep['amount']:,} so'm* hisobingizga qo'shildi!", reply_markup=main_kb())
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
    try:
        await bot.send_message(dep["user_id"], f"❌ To'lovingiz rad etildi.\n📋 #{short_id(ObjectId(str(did)))}\n\nAdmin bilan bog'laning.", reply_markup=main_kb())
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
@dp.message(F.text == "🛒 Robux sotib olish")
async def cmd_buy(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid = msg.from_user.id
    bal = await get_balance(uid)
    b = InlineKeyboardBuilder()
    for r, p in ROBUX_PRICES:
        b.button(text=f"{r}Rbx — {p // 1000}k", callback_data=f"buy_{r}")
    b.adjust(3)
    await msg.answer(
        f"🌟 *Assalomu alaykum!*\n💰 Balansingiz: *{bal:,} so'm*\n\n👇 Pastdagilardan birini tanlang:",
        reply_markup=b.as_markup()
    )

@dp.callback_query(lambda cb: bool(cb.data) and cb.data.startswith("buy_") and cb.data[len("buy_"):].isdigit())
async def cb_buy(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    missing = await not_subscribed_channels(uid)
    if missing:
        await cb.answer("❌ Avval barcha kanallarga obuna bo'ling!", show_alert=True)
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
    await cb.message.answer("🎮 Roblox nikingizni kiriting:", reply_markup=cancel_kb())
    await state.set_state(BuyFlow.nick)
    await cb.answer()

@dp.message(BuyFlow.nick)
async def buy_nick(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    nick = msg.text.strip()
    if len(nick) < 3:
        await msg.answer("❌ Nik kamida 3 ta belgi bo'lsin, qaytadan kiriting:")
        return
    await state.update_data(buy_nick=nick)
    await msg.answer("roblox parolingiz?", reply_markup=cancel_kb())
    await state.set_state(BuyFlow.mood)

@dp.message(BuyFlow.mood)
async def buy_mood(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
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
        f"😊 parolingiz: {esc_md(mood)}\n\n"
        f"Hammasi to'g'ri bo'lsa tasdiqlang:",
        reply_markup=b.as_markup()
    )

@dp.callback_query(F.data == "buy_redo")
async def cb_buy_redo(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer("🎮 Roblox nikingizni qayta kiriting:", reply_markup=cancel_kb())
    await state.set_state(BuyFlow.nick)
    await cb.answer()

@dp.callback_query(F.data == "buy_confirm")
async def cb_buy_confirm(cb: types.CallbackQuery, state: FSMContext):
    uid  = cb.from_user.id
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
        f"4️⃣ parolingiz: {esc_md(mood)}\n\n"
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
        reply_markup=main_kb()
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
    try:
        await bot.send_message(o["user_id"], f"🎉 *Robuxingiz tushdi!*\n🪙 {o['robux_amount']} Robux\n🎮 Nik: `{o.get('roblox_nick','-')}`\n📋 Buyurtma #{short_id(ObjectId(str(oid)))}", reply_markup=main_kb())
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
    try:
        await bot.send_message(o["user_id"], f"❌ Rad etildi.\n📋 Buyurtma #{short_id(ObjectId(str(oid)))}\n💰 {o['price_sum']:,} so'm hisobingizga qaytarildi.", reply_markup=main_kb())
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
@dp.message(F.text == "🔄 Tradelar")
async def cmd_trades(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    items = await active_trades()
    if not items:
        await msg.answer("🔄 Hozircha faol tradelar yo'q.\n\n➕ *Trade qo'shish* tugmasini bosing!")
        return
    await _send_trade_page(msg, items, 0, is_cb=False)

async def _send_trade_page(target, items, page, is_cb=True):
    t       = items[page]
    caption = (
        f"🔄 *TRADE E'LON #{short_id(t['_id'])}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"[{page+1}/{len(items)}]\n\n"
        f"👤 Foydalanuvchi: @{esc_md(t.get('username', '-'))}\n\n"
        f"📦 *Nomi:*\n{esc_md(t['name'])}\n\n"
        f"📝 *Tavsif:*\n{esc_md(t.get('bio') or '—')}\n\n"
        f"📅 Sana: {t['created_at']}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    b = InlineKeyboardBuilder()
    if page > 0:
        b.button(text="⬅️ Oldingi", callback_data=f"tp_{page-1}")
    if page < len(items) - 1:
        b.button(text="➡️ Keyingi", callback_data=f"tp_{page+1}")
    uname = t.get("username", "")
    if uname:
        b.button(text="💬 Murojaat", url=f"https://t.me/{uname}")
    b.button(text="🛒 Savatga solish", callback_data=f"add_trade_cart_{t['_id']}")
    b.adjust(2, 1, 1)
    if is_cb:
        await _send_or_edit(target, t.get("photo_id"), caption, b.as_markup())
    else:
        if t.get("photo_id"):
            await target.answer_photo(t["photo_id"], caption=caption, reply_markup=b.as_markup())
        else:
            await target.answer(caption, reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("tp_"))
async def cb_tp(cb: types.CallbackQuery):
    page  = int(cb.data.split("_")[1])
    items = await active_trades()
    if not items:
        await cb.answer("Tradelar yo'q!", show_alert=True)
        return
    page = max(0, min(page, len(items) - 1))
    await _send_trade_page(cb, items, page)
    await cb.answer()

@dp.message(F.text == "➕ Trade qo'shish")
async def cmd_trade_add(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    await msg.answer("📦 Trade sarlavhasi yozing\n(masalan: *Korblox x10 taklif qilaman*):", reply_markup=cancel_kb())
    await state.set_state(TradeAdd.name)

@dp.message(TradeAdd.name)
async def ta_name(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    if len(msg.text.strip()) < 5:
        await msg.answer("❌ Sarlavha kamida 5 ta belgi bo'lsin:")
        return
    await state.update_data(t_name=msg.text.strip())
    await msg.answer("📸 Rasm yuboring (ixtiyoriy):", reply_markup=skip_cancel_kb())
    await state.set_state(TradeAdd.photo)

@dp.message(TradeAdd.photo, F.photo)
async def ta_photo(msg: types.Message, state: FSMContext):
    await state.update_data(t_photo=msg.photo[-1].file_id)
    await msg.answer("📝 Bio yozing (nima taklif qilyapsiz, nima xohlaysiz) yoki o'tkazib yuboring:", reply_markup=skip_cancel_kb())
    await state.set_state(TradeAdd.bio)

@dp.message(TradeAdd.photo)
async def ta_no_photo(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    await state.update_data(t_photo=None)
    await msg.answer("📝 Bio yozing yoki o'tkazib yuboring:", reply_markup=skip_cancel_kb())
    await state.set_state(TradeAdd.bio)

@dp.message(TradeAdd.bio)
async def ta_bio(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    bio = "" if msg.text == "⏭ O'tkazib yuborish" else msg.text.strip()
    d        = await state.get_data()
    uid      = msg.from_user.id
    uname    = msg.from_user.username or "user"
    photo_id = d.get("t_photo")
    tid = await add_trade(uid, uname, "", d["t_name"], bio, photo_id)
    await state.clear()
    cap = f"🔄 Yangi trade #{short_id(tid)}\n👤 @{esc_md(uname)}\n📦 {esc_md(d['t_name'])}\n📝 {esc_md(bio or '-')}"
    await notify_admins(cap, photo_id=photo_id)
    await post_trade_to_channel(uname, d["t_name"], bio, photo_id)
    await msg.answer(f"✅ Trade e'lon qilindi! *#{short_id(tid)}*", reply_markup=main_kb())

@dp.callback_query(F.data.startswith("etrade_"))
async def cb_etrade(cb: types.CallbackQuery, state: FSMContext):
    tid = cb.data.split("_")[1]
    t   = await get_trade(tid)
    if not t or (t["user_id"] != cb.from_user.id and not is_admin(cb.from_user.id)):
        await cb.answer("Ruxsat yo'q!", show_alert=True)
        return
    await state.update_data(edit_trade_id=tid)
    await cb.message.answer("✏️ Yangi nom yozing:", reply_markup=cancel_kb())
    await state.set_state(TradeEdit.name)
    await cb.answer()

@dp.message(TradeEdit.name)
async def etrade_name(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    await state.update_data(new_name=msg.text.strip())
    await msg.answer("📝 Yangi bio yozing:", reply_markup=cancel_kb())
    await state.set_state(TradeEdit.bio)

@dp.message(TradeEdit.bio)
async def etrade_bio(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    d = await state.get_data()
    await edit_trade(d["edit_trade_id"], d["new_name"], msg.text.strip())
    await state.clear()
    await msg.answer("✅ Trade yangilandi!", reply_markup=main_kb())

@dp.callback_query(F.data.startswith("dtrade_"))
async def cb_dtrade(cb: types.CallbackQuery):
    tid = cb.data.split("_")[1]
    t   = await get_trade(tid)
    if not t or (t["user_id"] != cb.from_user.id and not is_admin(cb.from_user.id)):
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

# Savatga qo'shish — trade
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
@dp.message(F.text == "📊 Sotuvlar")
async def cmd_sales(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    items = await active_sales()
    if not items:
        await msg.answer("📊 Hozircha sotuvdagi buyumlar yo'q.\n\n➕ *Sotish qo'shish* tugmasini bosing!")
        return
    await _send_sale_page(msg, items, 0, is_cb=False)

async def _send_sale_page(target, items, page, is_cb=True):
    s       = items[page]
    caption = (
        f"🛍 *SOTUV E'LON #{short_id(s['_id'])}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"[{page+1}/{len(items)}]\n\n"
        f"👤 Foydalanuvchi: @{esc_md(s.get('username', '-'))}\n\n"
        f"📦 *Nomi:*\n{esc_md(s['name'])}\n\n"
        f"📝 *Tavsif:*\n{esc_md(s.get('bio') or '—')}\n\n"
        f"💰 *Narxi:* {s['price']:,} {s['currency']}\n\n"
        f"📅 Sana: {s['created_at']}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    b = InlineKeyboardBuilder()
    if page > 0:
        b.button(text="⬅️ Oldingi", callback_data=f"sp_{page-1}")
    if page < len(items) - 1:
        b.button(text="➡️ Keyingi", callback_data=f"sp_{page+1}")
    uname = s.get("username", "")
    if uname:
        b.button(text="💬 Murojaat", url=f"https://t.me/{uname}")
    b.button(text="🛒 Savatga solish", callback_data=f"add_sale_cart_{s['_id']}")
    b.adjust(2, 1, 1)
    if is_cb:
        await _send_or_edit(target, s.get("photo_id"), caption, b.as_markup())
    else:
        if s.get("photo_id"):
            await target.answer_photo(s["photo_id"], caption=caption, reply_markup=b.as_markup())
        else:
            await target.answer(caption, reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("sp_"))
async def cb_sp(cb: types.CallbackQuery):
    page  = int(cb.data.split("_")[1])
    items = await active_sales()
    if not items:
        await cb.answer("Sotuvlar yo'q!", show_alert=True)
        return
    page = max(0, min(page, len(items) - 1))
    await _send_sale_page(cb, items, page)
    await cb.answer()

@dp.message(F.text == "➕ Sotish qo'shish")
async def cmd_sale_add(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    await msg.answer("📦 Nima sotmoqchisiz? Nom yozing:", reply_markup=cancel_kb())
    await state.set_state(SaleAdd.name)

@dp.message(SaleAdd.name)
async def sa_name(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    await state.update_data(s_name=msg.text.strip())
    await msg.answer("📸 Rasm yuboring (ixtiyoriy):", reply_markup=skip_cancel_kb())
    await state.set_state(SaleAdd.photo)

@dp.message(SaleAdd.photo, F.photo)
async def sa_photo(msg: types.Message, state: FSMContext):
    await state.update_data(s_photo=msg.photo[-1].file_id)
    await msg.answer("📝 Bio yozing (buyum haqida) yoki o'tkazib yuboring:", reply_markup=skip_cancel_kb())
    await state.set_state(SaleAdd.bio)

@dp.message(SaleAdd.photo)
async def sa_no_photo(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    await state.update_data(s_photo=None)
    await msg.answer("📝 Bio yozing yoki o'tkazib yuboring:", reply_markup=skip_cancel_kb())
    await state.set_state(SaleAdd.bio)

@dp.message(SaleAdd.bio)
async def sa_bio(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    bio = "" if msg.text == "⏭ O'tkazib yuborish" else msg.text.strip()
    await state.update_data(s_bio=bio)
    await _ask_currency(msg, state)

async def _ask_currency(msg: types.Message, state: FSMContext):
    b = InlineKeyboardBuilder()
    b.button(text="💵 So'm (UZS)", callback_data="sc_som")
    b.button(text="🪙 Robux",      callback_data="sc_robux")
    b.adjust(2)
    await msg.answer("💱 Valyutani tanlang:", reply_markup=b.as_markup())
    await state.set_state(SaleAdd.currency)

@dp.callback_query(F.data.startswith("sc_"))
async def cb_sc(cb: types.CallbackQuery, state: FSMContext):
    cur = "so'm" if cb.data == "sc_som" else "Robux"
    await state.update_data(s_currency=cur)
    await cb.message.answer(f"💰 Narxni yozing ({cur} da):", reply_markup=cancel_kb())
    await state.set_state(SaleAdd.price)
    await cb.answer()

@dp.message(SaleAdd.price)
async def sa_price(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    txt = msg.text.strip().replace(" ", "").replace(",", "")
    if not txt.isdigit():
        await msg.answer("❌ Faqat raqam kiriting:")
        return
    d     = await state.get_data()
    uid   = msg.from_user.id
    uname = msg.from_user.username or "user"
    bio   = d.get("s_bio", "")
    sid   = await add_sale(uid, uname, "", d["s_name"], bio, d.get("s_photo"), d["s_currency"], int(txt))
    await state.clear()
    cap = f"🛍 Yangi sotuv #{short_id(sid)}\n👤 @{esc_md(uname)}\n📦 {esc_md(d['s_name'])}\n📝 {esc_md(bio or '-')}\n💰 {int(txt):,} {d['s_currency']}"
    await notify_admins(cap, photo_id=d.get("s_photo"))
    await post_sale_to_channel(uname, d["s_name"], bio, int(txt), d["s_currency"], d.get("s_photo"))
    await msg.answer(
        f"✅ Sotuv e'lon qilindi! *#{short_id(sid)}*\n📦 {d['s_name']}\n💰 {int(txt):,} {d['s_currency']}",
        reply_markup=main_kb()
    )

@dp.callback_query(F.data.startswith("esale_"))
async def cb_esale(cb: types.CallbackQuery, state: FSMContext):
    sid = cb.data.split("_")[1]
    s   = await get_sale(sid)
    if not s or (s["user_id"] != cb.from_user.id and not is_admin(cb.from_user.id)):
        await cb.answer("Ruxsat yo'q!", show_alert=True)
        return
    await state.update_data(edit_sale_id=sid)
    await cb.message.answer("✏️ Yangi nom yozing:", reply_markup=cancel_kb())
    await state.set_state(SaleEdit.name)
    await cb.answer()

@dp.message(SaleEdit.name)
async def esale_name(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    await state.update_data(new_name=msg.text.strip())
    await msg.answer("💰 Yangi narx (raqam):", reply_markup=cancel_kb())
    await state.set_state(SaleEdit.price)

@dp.message(SaleEdit.price)
async def esale_price(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    txt = msg.text.strip().replace(" ", "")
    if not txt.isdigit():
        await msg.answer("❌ Faqat raqam:")
        return
    d = await state.get_data()
    await edit_sale(d["edit_sale_id"], d["new_name"], int(txt))
    await state.clear()
    await msg.answer("✅ Sotuv yangilandi!", reply_markup=main_kb())

@dp.callback_query(F.data.startswith("dsale_"))
async def cb_dsale(cb: types.CallbackQuery):
    sid = cb.data.split("_")[1]
    s   = await get_sale(sid)
    if not s or (s["user_id"] != cb.from_user.id and not is_admin(cb.from_user.id)):
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

# Savatga qo'shish — sotuv
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
@dp.message(F.text == "🛒 Savat")
async def cmd_cart(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Trade savati", callback_data="cart_trades")
    b.button(text="🛍 Sotuv savati", callback_data="cart_sales")
    b.adjust(2)
    await msg.answer(
        "🛒 *Savat*\n\nQaysi savatni ko'rmoqchisiz?",
        reply_markup=b.as_markup()
    )

@dp.callback_query(F.data == "cart_trades")
async def cb_cart_trades(cb: types.CallbackQuery):
    uid   = cb.from_user.id
    items = await get_trade_cart(uid)
    if not items:
        await cb.answer("🛒 Trade savatingiz bo'sh!", show_alert=True)
        return
    for i, t in enumerate(items):
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
    for i, s in enumerate(items):
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
@dp.message(F.text == "🌐 Online Traderlar")
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
        "Online trader qo'shish yoki ko'rish uchun "
        "quyidagi bo'limlarni bosing:",
        reply_markup=b.as_markup()
    )

# ─── Trader qo'shish ───────────────────────────────────
@dp.callback_query(F.data == "ot_add")
async def cb_ot_add(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    existing = await get_online_trader(uid)
    if existing:
        # allaqachon qo'shilgan — tahrirlashga yo'naltir
        b = InlineKeyboardBuilder()
        b.button(text="✏️ Ma'lumotlarni yangilash", callback_data="ot_edit")
        b.button(text="🔙 Orqaga", callback_data="ot_back")
        b.adjust(1)
        await cb.message.answer(
            "ℹ️ Siz allaqachon online trader sifatida ro'yxatdasiz.\n"
            "Ma'lumotlarni yangilash uchun quyidagi tugmani bosing:",
            reply_markup=b.as_markup()
        )
        await cb.answer()
        return
    await cb.message.answer(
        "📸 Rasm yuboring (ixtiyoriy, o'tkazib yuborsa ham bo'ladi):",
        reply_markup=skip_cancel_kb()
    )
    await state.set_state(OnlineTraderAdd.photo)
    await cb.answer()

@dp.message(OnlineTraderAdd.photo, F.photo)
async def ot_add_photo(msg: types.Message, state: FSMContext):
    await state.update_data(ot_photo=msg.photo[-1].file_id)
    await msg.answer("🎮 Robloxdagi nikinigiz nima?", reply_markup=cancel_kb())
    await state.set_state(OnlineTraderAdd.nick)

@dp.message(OnlineTraderAdd.photo)
async def ot_add_no_photo(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    await state.update_data(ot_photo=None)
    await msg.answer("🎮 Robloxdagi nikinigiz nima?", reply_markup=cancel_kb())
    await state.set_state(OnlineTraderAdd.nick)

@dp.message(OnlineTraderAdd.nick)
async def ot_add_nick(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    await state.update_data(ot_nick=msg.text.strip())
    await msg.answer("📝 Bio yozing (o'zingiz haqida qisqacha):", reply_markup=cancel_kb())
    await state.set_state(OnlineTraderAdd.bio)

@dp.message(OnlineTraderAdd.bio)
async def ot_add_bio(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    d      = await state.get_data()
    uid    = msg.from_user.id
    uname  = msg.from_user.username or "user"
    await upsert_online_trader(uid, uname, d["ot_nick"], msg.text.strip(), d.get("ot_photo"))
    await post_online_trader_to_channel(uname, d["ot_nick"], msg.text.strip(), d.get("ot_photo"))
    await state.clear()
    await msg.answer(
        "✅ *Siz Online Traderlar ro'yxatiga qo'shildingiz!*\n\n"
        "🟢 Holat: Online\n"
        "Holatni o'zgartirish uchun: 🌐 Online Traderlar → 🟢 Online / Offline",
        reply_markup=main_kb()
    )

# ─── Online traderlarni ko'rish ────────────────────────
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

# ─── Online/Offline almashtirish ───────────────────────
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

# ─── Trader ma'lumotlarini yangilash ───────────────────
@dp.callback_query(F.data == "ot_edit")
async def cb_ot_edit(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer(
        "🎮 Yangi Roblox nikinigizni kiriting:",
        reply_markup=cancel_kb()
    )
    await state.set_state(OnlineTraderEdit.nick)
    await cb.answer()

@dp.message(OnlineTraderEdit.nick)
async def ot_edit_nick(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    await state.update_data(ot_new_nick=msg.text.strip())
    await msg.answer("📝 Yangi bio yozing:", reply_markup=cancel_kb())
    await state.set_state(OnlineTraderEdit.bio)

@dp.message(OnlineTraderEdit.bio)
async def ot_edit_bio(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    d     = await state.get_data()
    uid   = msg.from_user.id
    uname = msg.from_user.username or "user"
    doc   = await get_online_trader(uid)
    photo = doc.get("photo_id") if doc else None
    await upsert_online_trader(uid, uname, d["ot_new_nick"], msg.text.strip(), photo)
    await state.clear()
    await msg.answer("✅ Ma'lumotlaringiz yangilandi!", reply_markup=main_kb())

@dp.callback_query(F.data == "ot_back")
async def cb_ot_back(cb: types.CallbackQuery):
    b = InlineKeyboardBuilder()
    b.button(text="➕ Trader qo'shish", callback_data="ot_add")
    b.button(text="👥 Online traderlarni ko'rish", callback_data="ot_list")
    b.button(text="🟢 Online / Offline", callback_data="ot_toggle")
    b.adjust(1)
    try:
        await cb.message.edit_text(
            "🌐 *Assalomu alaykum hurmatli foydalanuvchi!*\n\n"
            "Online trader qo'shish yoki ko'rish uchun "
            "quyidagi bo'limlarni bosing:",
            reply_markup=b.as_markup()
        )
    except Exception:
        await cb.message.answer(
            "🌐 *Assalomu alaykum hurmatli foydalanuvchi!*\n\n"
            "Online trader qo'shish yoki ko'rish uchun "
            "quyidagi bo'limlarni bosing:",
            reply_markup=b.as_markup()
        )
    await cb.answer()

# ═══════════════════════════════════════════════════════
# CHAT
# ═══════════════════════════════════════════════════════
@dp.message(F.text == "💬 Chat")
async def cmd_chat(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    b = InlineKeyboardBuilder()
    b.button(text="💬 Chatga kirish", url=CHAT_LINK)
    await msg.answer("💬 Rasmiy chatimizga xush kelibsiz!", reply_markup=b.as_markup())

# ═══════════════════════════════════════════════════════
# SHARTNOMA QILISH
# ═══════════════════════════════════════════════════════
@dp.message(F.text == "📜 Shartnoma qilish")
async def cmd_contract(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    b = InlineKeyboardBuilder()
    b.button(text="✉️ Adminga xabar yuborish", callback_data="send_admin_msg")
    b.adjust(1)
    await msg.answer(
        "📜 *Shartnoma qilish*\n\n"
        "👤 Admin: @notalonet\n\n"
        "💬 Admin bilan shartnoma asosida ishlash uchun quyidagi tugmani bosing.\n"
        "📸 Rasm ham yuborishingiz mumkin (ixtiyoriy).\n"
        "⏰ 24 soatda 1 marta xabar yuborish mumkin.",
        reply_markup=b.as_markup()
    )

@dp.callback_query(F.data == "send_admin_msg")
async def cb_send_admin_msg(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    ok = await check_cooldown(uid, "contract")
    if not ok:
        rem = await cooldown_remaining(uid, "contract")
        await cb.answer(f"⏰ 24 soatda 1 marta yozsa bo'ladi!\n{rem} kutib turing.", show_alert=True)
        return
    await cb.message.answer("📸 Rasm yuboring (ixtiyoriy, o'tkazib yuborish mumkin):", reply_markup=skip_cancel_kb())
    await state.set_state(ContactAdmin.photo)
    await cb.answer()

@dp.message(ContactAdmin.photo, F.photo)
async def contact_photo(msg: types.Message, state: FSMContext):
    await state.update_data(ca_photo=msg.photo[-1].file_id)
    await msg.answer("✍️ Xabaringizni yozing:", reply_markup=cancel_kb())
    await state.set_state(ContactAdmin.message)

@dp.message(ContactAdmin.photo)
async def contact_no_photo(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    await state.update_data(ca_photo=None)
    await msg.answer("✍️ Xabaringizni yozing:", reply_markup=cancel_kb())
    await state.set_state(ContactAdmin.message)

@dp.message(ContactAdmin.message)
async def contact_admin_text(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    uid   = msg.from_user.id
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
    await msg.answer("✅ Xabaringiz adminga yuborildi! Tez orada javob beriladi.", reply_markup=main_kb())

# ═══════════════════════════════════════════════════════
# ADMINLIK XIZMATI
# ═══════════════════════════════════════════════════════
@dp.message(F.text == "🛡 Adminlik xizmati")
async def cmd_admin_service(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    b = InlineKeyboardBuilder()
    b.button(text="📩 Adminga yozish", url="https://t.me/notalonet")
    b.adjust(1)
    await msg.answer(
        "🛡 *Adminlik xizmati*\n\n"
        "👤 Admin: @notalonet\n\n"
        "Adminlik xizmati uchun to'g'ridan-to'g'ri adminga murojaat qiling.\n"
        "Quyidagi tugmani bosib admin lichkasiga o'ting:",
        reply_markup=b.as_markup()
    )

# ═══════════════════════════════════════════════════════
# TAKLIF BERISH
# ═══════════════════════════════════════════════════════
@dp.message(F.text == "💡 Taklif berish")
async def cmd_suggest(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    await msg.answer(
        "💡 *Bot uchun taklif berish*\n\n"
        "❓ Bu bo'limda bot qanday qilsa yaxshi bo'ladi?\n"
        "Qanday narsalar qo'shaylik botga?\n\n"
        "📸 Rasm ham tashlasangiz bo'ladi (ixtiyoriy).\n"
        "⏭ O'tkazib yuborish ham mumkin.\n"
        "⏰ 24 soatda 1 marta taklif berish mumkin.\n\n"
        "Shularni yozib qoldiring 👇",
        reply_markup=skip_cancel_kb()
    )
    await state.set_state(SuggestBot.photo)

@dp.message(SuggestBot.photo, F.photo)
async def suggest_photo(msg: types.Message, state: FSMContext):
    await state.update_data(sg_photo=msg.photo[-1].file_id)
    await msg.answer("✍️ Taklifingizni yozing:", reply_markup=cancel_kb())
    await state.set_state(SuggestBot.message)

@dp.message(SuggestBot.photo)
async def suggest_no_photo(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    await state.update_data(sg_photo=None)
    await msg.answer("✍️ Taklifingizni yozing:", reply_markup=cancel_kb())
    await state.set_state(SuggestBot.message)

@dp.message(SuggestBot.message)
async def suggest_message(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    uid   = msg.from_user.id
    uname = msg.from_user.username or "-"
    fname = msg.from_user.full_name
    ok = await check_cooldown(uid, "suggest")
    if not ok:
        rem = await cooldown_remaining(uid, "suggest")
        await state.clear()
        await msg.answer(f"⏰ 24 soatda 1 marta taklif bersa bo'ladi!\n{rem} kutib turing.", reply_markup=main_kb())
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
    await msg.answer(
        "✅ *Rahmat! Fikringiz e'tiborsiz qolmaydi* 🙏\n\n"
        "Taklifingiz adminimizga yuborildi!",
        reply_markup=main_kb()
    )

# ═══════════════════════════════════════════════════════
# REKLAMA QILISH
# ═══════════════════════════════════════════════════════
AD_PRICE = 5000

@dp.message(F.text == "📣 Reklama qilish")
async def cmd_ad(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    uid = msg.from_user.id
    bal = await get_balance(uid)
    b = InlineKeyboardBuilder()
    b.button(text="📣 Reklama berish", callback_data="ad_start")
    b.adjust(1)
    await msg.answer(
        f"📣 *Reklama qilish*\n\n"
        f"💰 Reklama narxi: *{AD_PRICE:,} so'm*\n"
        f"👛 Sizning balansingiz: *{bal:,} so'm*\n\n"
        f"Reklamangiz barcha bot foydalanuvchilariga yuboriladi!\n"
        f"📸 Rasm + bio shaklida chiqadi.\n\n"
        f"Reklama berish uchun tugmani bosing:",
        reply_markup=b.as_markup()
    )

@dp.callback_query(F.data == "ad_start")
async def cb_ad_start(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    bal = await get_balance(uid)
    if bal < AD_PRICE:
        await cb.answer(
            f"❌ Hisobingiz yetarli emas!\nKerak: {AD_PRICE:,} so'm\nBalans: {bal:,} so'm\n\nAvval hisob to'ldiring.",
            show_alert=True
        )
        return
    await cb.message.answer("📸 Reklama uchun rasm yuboring:", reply_markup=cancel_kb())
    await state.set_state(AdFlow.photo)
    await cb.answer()

@dp.message(AdFlow.photo, F.photo)
async def ad_photo(msg: types.Message, state: FSMContext):
    await state.update_data(ad_photo=msg.photo[-1].file_id)
    await msg.answer(
        "📝 Reklama matnini (bio) yozing:\n\n"
        "Masalan: Firma nomi, narxlar, link yoki aloqa.",
        reply_markup=cancel_kb()
    )
    await state.set_state(AdFlow.bio)

@dp.message(AdFlow.photo)
async def ad_no_photo(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    await msg.answer("❌ Iltimos rasm yuboring:")

@dp.message(AdFlow.bio)
async def ad_bio(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    uid   = msg.from_user.id
    uname = msg.from_user.username or "user"
    d     = await state.get_data()
    photo = d.get("ad_photo")
    bio   = msg.text.strip()
    bal = await get_balance(uid)
    if bal < AD_PRICE:
        await state.clear()
        await msg.answer("❌ Hisobingiz yetarli emas!", reply_markup=main_kb())
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
        f"📤 Yuborildi: {sent}/{len(uids)} ta foydalanuvchiga"
    )
    await msg.answer(
        f"✅ Reklamangiz *{sent}* ta foydalanuvchiga yuborildi!\n"
        f"💰 Hisobingizdan {AD_PRICE:,} so'm yechildi.",
        reply_markup=main_kb()
    )

# ═══════════════════════════════════════════════════════
# 🔍 QIDIRUV BO'LIMI  (ID orqali / Ism orqali)
# ═══════════════════════════════════════════════════════
class SearchFlow(StatesGroup):
    by_id   = State()
    by_name = State()

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

@dp.message(F.text == "🔍 Qidiruv")
async def cmd_search(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    await state.clear()
    await msg.answer(
        "🔍 *Qidiruv bo'limi*\n\n"
        "Qaysi usul orqali qidirmoqchisiz?\n\n"
        "🆔 *ID orqali* — Telegram ID yoki e'lon ID (masalan: `123456789` yoki `A1B2C3`)\n"
        "📝 *Ism orqali* — Roblox nik, e'lon nomi yoki @username",
        reply_markup=search_menu_kb()
    )

@dp.callback_query(F.data == "search_by_id")
async def cb_search_by_id(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer(
        "🆔 *ID orqali qidiruv*\n\n"
        "Qidirish uchun ID yuboring:\n"
        "• Foydalanuvchi Telegram ID (masalan: `123456789`)\n"
        "• Trade/Sotuv e'lon ID (masalan: `A1B2C3`)",
        reply_markup=cancel_kb()
    )
    await state.set_state(SearchFlow.by_id)
    await cb.answer()

@dp.callback_query(F.data == "search_by_name")
async def cb_search_by_name(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer(
        "📝 *Ism orqali qidiruv*\n\n"
        "Roblox nik, e'lon nomi yoki @username yozing:",
        reply_markup=cancel_kb()
    )
    await state.set_state(SearchFlow.by_name)
    await cb.answer()

@dp.message(SearchFlow.by_id)
async def search_by_id_handler(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    query = msg.text.strip().lstrip("@")
    await state.clear()
    found = False

    # 1) Telegram user_id bo'yicha qidirish — odamni topish
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

    # 2) Qisqa e'lon ID (short_id) bo'yicha qidirish — trade/sotuv/online trader
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
        await msg.answer("❌ Hech narsa topilmadi. Boshqa ID bilan urinib ko'ring.", reply_markup=main_kb())
        return
    await msg.answer("✅ Qidiruv yakunlandi.", reply_markup=main_kb())

@dp.message(SearchFlow.by_name)
async def search_by_name_handler(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    query = msg.text.strip().lstrip("@")
    await state.clear()
    if len(query) < 2:
        await msg.answer("❌ Kamida 2 ta belgi kiriting:", reply_markup=main_kb())
        return

    import re as _re
    pattern = _re.compile(_re.escape(query), _re.IGNORECASE)
    found = False

    trade_matches = [t async for t in trades.find({"status": "active", "name": {"$regex": pattern}}).limit(10)]
    for t in trade_matches:
        found = True
        await _send_trade_result(msg, t)

    sale_matches = [s async for s in sales.find({"status": "active", "name": {"$regex": pattern}}).limit(10)]
    for s in sale_matches:
        found = True
        await _send_sale_result(msg, s)

    ot_matches = [t async for t in online_traders.find({
        "$or": [
            {"roblox_nick": {"$regex": pattern}},
            {"username":    {"$regex": pattern}},
        ]
    }).limit(10)]
    for t in ot_matches:
        found = True
        await _send_ot_result(msg, t)

    if not found:
        await msg.answer("❌ Hech narsa topilmadi. Boshqa nom bilan urinib ko'ring.", reply_markup=main_kb())
        return
    await msg.answer("✅ Qidiruv yakunlandi.", reply_markup=main_kb())

# ═══════════════════════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════════════════════
@dp.message(Command("admin"))
async def cmd_admin(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("❌ Ruxsat yo'q!")
        return
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
    b.adjust(2, 2, 1)
    await msg.answer(
        f"🛠 *Admin Panel*\n\n👥 Foydalanuvchilar: *{cnt}*\n"
        f"📦 Kutayotgan buyurtmalar: *{len(or_)}*\n"
        f"🔄 Faol tradelar: *{len(tr)}*\n🛍 Faol sotuvlar: *{len(sl)}*",
        reply_markup=b.as_markup()
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
        caption = f"🔄 *#{short_id(t['_id'])}* {esc_md(t['name'])}\n👤 @{esc_md(t.get('username','-'))}\n📝 {esc_md(t['bio'])}"
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
        caption = f"🛍 *#{short_id(s['_id'])}* {esc_md(s['name'])}\n👤 @{esc_md(s.get('username','-'))}\n📝 {esc_md(s.get('bio') or '-')}\n💰 {s['price']:,} {s['currency']}"
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
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    parts = msg.text.strip().split()
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await msg.answer("❌ Format: `<user_id> <summa>`")
        return
    uid, amt = int(parts[0]), int(parts[1])
    await users.update_one({"user_id": uid}, {"$inc": {"balance": amt}})
    try:
        await bot.send_message(uid, f"💰 Hisobingizga *{amt:,} so'm* qo'shildi!", reply_markup=main_kb())
    except Exception:
        pass
    await state.clear()
    await msg.answer(f"✅ {uid} ga {amt:,} so'm qo'shildi.", reply_markup=main_kb())

@dp.message(Command("addbalance"))
async def cmd_addbalance(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("❌ Ruxsat yo'q!")
        return
    parts = msg.text.split()
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await msg.answer("❌ Format: /addbalance <user_id> <summa>")
        return
    uid, amt = int(parts[1]), int(parts[2])
    await users.update_one({"user_id": uid}, {"$inc": {"balance": amt}})
    try:
        await bot.send_message(uid, f"💰 Hisobingizga *{amt:,} so'm* qo'shildi!", reply_markup=main_kb())
    except Exception:
        pass
    await msg.answer(f"✅ {uid} ga {amt:,} so'm qo'shildi.")

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
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    await state.update_data(bc_photo=None)
    await msg.answer("📝 Xabar matnini yozing:", reply_markup=cancel_kb())
    await state.set_state(Broadcast.text)

@dp.message(Broadcast.text)
async def bc_text(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
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
    await msg.answer(f"✅ Xabar *{sent}/{len(uids)}* ta foydalanuvchiga yuborildi!", reply_markup=main_kb())

# ═══════════════════════════════════════════════════════
# WEBHOOK (Render Web Service uchun)
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
