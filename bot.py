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
BOT_TOKEN        = os.getenv("BOT_TOKEN")
ADMIN_ID         = int(os.getenv("8667862086", "0"))
MONGO_URI        = os.getenv("MONGO_URI")
REQUIRED_CHANNEL  = os.getenv("CHANNEL", "@bulldrop_n1")
REQUIRED_CHANNEL2 = os.getenv("CHANNEL2", "@uzbekroblox")
CARD_NUMBER      = os.getenv("CARD_NUMBER", "5614-6820-9134-4749")
CARD_OWNER       = os.getenv("CARD_OWNER", "Nurboyev.N")
CHAT_LINK        = os.getenv("CHAT_LINK", "https://t.me/roblox_uz")

# ═══════════════════════════════════════════════════════
# MONGODB
# ═══════════════════════════════════════════════════════
mongo_client = AsyncIOMotorClient(MONGO_URI)
mdb          = mongo_client["roblox_bot"]
users        = mdb["users"]
deposits     = mdb["deposits"]
orders       = mdb["orders"]
trades       = mdb["trades"]
sales        = mdb["sales"]
suggestions  = mdb["suggestions"]
ads          = mdb["ads"]
cooldowns    = mdb["cooldowns"]
autoxabar_db = mdb["autoxabar"]   # autoxabar sozlamalari

async def init_indexes():
    await users.create_index("user_id", unique=True)
    await deposits.create_index("user_id")
    await orders.create_index("user_id")
    await trades.create_index([("user_id", 1), ("status", 1)])
    await sales.create_index([("user_id", 1), ("status", 1)])
    await suggestions.create_index("user_id")
    await ads.create_index("user_id")
    await cooldowns.create_index([("user_id", 1), ("action", 1)], unique=True)

# ═══════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════
def now():
    return datetime.now().strftime("%d.%m.%Y %H:%M")

def short_id(oid):
    return str(oid)[-6:].upper()

def esc_md(text) -> str:
    """Telegram legacy Markdown uchun maxsus belgilarni escape qiladi
    (aks holda foydalanuvchi yuborgan _, *, `, [ belgilari bo'lgan
    xabarlar 'can't parse entities' xatosi bilan yuborilmay qoladi)."""
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
    """True = ruxsat (cooldown o'tgan), False = hali kutish kerak."""
    from datetime import datetime as dt
    now_ts = dt.now().timestamp()
    rec = await cooldowns.find_one({"user_id": uid, "action": action})
    if rec:
        last = rec.get("last_at", 0)
        if now_ts - last < 86400:  # 24 soat
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

class ContactAdmin(StatesGroup):
    message = State()

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

class AutoxabarFlow(StatesGroup):
    login_phone  = State()   # telefon raqam
    login_code   = State()   # Telegram kodi
    login_2fa    = State()   # 2FA parol
    photo        = State()   # reklama rasmi
    text         = State()   # reklama matni
    confirm_edit = State()   # boshqa vaqt kiritish

# ═══════════════════════════════════════════════════════
# BOT + DP
# ═══════════════════════════════════════════════════════
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp  = Dispatcher(storage=MemoryStorage())

# ═══════════════════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════════════════
def sub_kb():
    b = InlineKeyboardBuilder()
    b.button(text="📢 1-kanalga obuna bo'lish", url=f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}")
    b.button(text="📢 2-kanalga obuna bo'lish", url=f"https://t.me/{REQUIRED_CHANNEL2.lstrip('@')}")
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
    b.button(text="💬 Chat")
    b.button(text="📜 Shartnoma qilish")
    b.button(text="📣 Reklama qilish")
    b.button(text="🛡 Adminlik xizmati")
    b.button(text="💡 Taklif berish")
    b.button(text="📢 Autoxabar")
    b.adjust(2, 2, 2, 2, 1, 2, 1)
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
async def is_sub(uid: int) -> bool:
    try:
        m1 = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=uid)
        ok1 = m1.status not in ["left", "kicked", "banned"]
    except Exception as e:
        logging.error(f"Sub check xato (1-kanal): {e}")
        ok1 = True   # xato bo'lsa o'tkazib yubor
    try:
        m2 = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL2, user_id=uid)
        ok2 = m2.status not in ["left", "kicked", "banned"]
    except Exception as e:
        logging.error(f"Sub check xato (2-kanal): {e}")
        ok2 = True   # xato bo'lsa o'tkazib yubor
    return ok1 and ok2

async def check_access(msg: types.Message, state: FSMContext) -> bool:
    uid = msg.from_user.id
    if not await is_sub(uid):
        await msg.answer("❌ Avval ikkala kanalga ham obuna bo'ling!", reply_markup=sub_kb())
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

# ═══════════════════════════════════════════════════════
# /START + OBUNA
# ═══════════════════════════════════════════════════════
@dp.message(Command("start"))
async def cmd_start(msg: types.Message, state: FSMContext):
    uid = msg.from_user.id
    if not await is_sub(uid):
        await msg.answer("👋 Salom! Botdan foydalanish uchun avval ikkala kanalimizga ham obuna bo'ling!", reply_markup=sub_kb())
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
    if not await is_sub(uid):
        await cb.answer("❌ Hali ikkala kanalga ham obuna bo'lmagansiz!", show_alert=True)
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
    caption = f"🔄 *{t['name']}* [{page+1}/{len(items)}]\n📝 {t['bio']}\n📅 {t['created_at']}"
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
    caption = f"🛍 *{s['name']}* [{page+1}/{len(items)}]\n💰 {s['price']:,} {s['currency']}\n📅 {s['created_at']}"
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
    if not await is_sub(cb.from_user.id):
        await cb.answer("❌ Avval kanalga obuna bo'ling!", show_alert=True)
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
    text = (
        f"💳 *To'lov ma'lumotlari*\n\n"
        f"💰 Miqdor: *{amount:,} so'm*\n\n"
        f"🏦 Karta raqami:\n`{CARD_NUMBER}`\n\n"
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
    u        = await get_user(uid)
    d        = await state.get_data()
    amount   = d.get("dep_amount", 0)
    photo_id = msg.photo[-1].file_id
    did      = await add_deposit(uid, uname, "", amount, photo_id)
    b = InlineKeyboardBuilder()
    b.button(text="✅ Tasdiqlash", callback_data=f"dok_{did}")
    b.button(text="❌ Rad etish",  callback_data=f"dno_{did}")
    b.adjust(2)
    try:
        await bot.send_photo(
            ADMIN_ID, photo_id,
            caption=(
                f"💰 *To'lov #{short_id(did)}*\n\n"
                f"👤 @{esc_md(uname)} (`{uid}`)\n"
                f"💵 Miqdor: *{amount:,} so'm*\n🕐 {now()}"
            ),
            reply_markup=b.as_markup()
        )
    except Exception as e:
        logging.error(f"Admin ga xato: {e}")
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
    if cb.from_user.id != ADMIN_ID:
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
    if cb.from_user.id != ADMIN_ID:
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

@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    if not await is_sub(uid):
        await cb.answer("❌ Avval ikkala kanalga ham obuna bo'ling!", show_alert=True)
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
    await msg.answer("parolingz?", reply_markup=cancel_kb())
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
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🛒 *Robux buyurtma #{short_id(oid)}*\n\n"
            f"1️⃣ Nik: `{esc_md(nick)}`\n"
            f"2️⃣ Robux: *{robux}*\n"
            f"3️⃣ Narx: *{price:,} so'm*\n"
            f"4️⃣ parolingiz: {esc_md(mood)}\n\n"
            f"👤 @{esc_md(cb.from_user.username or '-')} (`{uid}`)\n🕐 {now()}",
            reply_markup=b.as_markup()
        )
    except Exception:
        pass
    await state.clear()
    await cb.message.answer(
        f"✅ *Buyurtmangiz qabul qilindi!*\n\n"
        f"🪙 Robux: *{robux}*\n"
        f"💵 To'langan: *{price:,} so'm*\n"
        f"🎮 Nik: `{esc_md(nick)}`\n"
        f"📋 Buyurtma #{short_id(oid)}\n\n"
        f"⏳ Admin javobini kuting. ungacha robloxda 2 bosqichli tasdiqlashni ochirib qoying!",
        reply_markup=main_kb()
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("ook_"))
async def cb_ook(cb: types.CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
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
    if cb.from_user.id != ADMIN_ID:
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
    b.adjust(2, 1)
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
    await msg.answer("📝 Bio yozing (nima taklif qilyapsiz, nima xohlaysiz) yoki o'tkazib yuboring:", reply_markup=skip_cancel_kb())
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
    try:
        cap = f"🔄 Yangi trade #{short_id(tid)}\n👤 @{esc_md(uname)}\n📦 {esc_md(d['t_name'])}\n📝 {esc_md(bio or '-')}"
        if photo_id:
            await bot.send_photo(ADMIN_ID, photo_id, caption=cap)
        else:
            await bot.send_message(ADMIN_ID, cap)
    except Exception:
        pass
    await msg.answer(f"✅ Trade e'lon qilindi! *#{short_id(tid)}*", reply_markup=main_kb())

@dp.callback_query(F.data.startswith("etrade_"))
async def cb_etrade(cb: types.CallbackQuery, state: FSMContext):
    tid = cb.data.split("_")[1]
    t   = await get_trade(tid)
    if not t or (t["user_id"] != cb.from_user.id and cb.from_user.id != ADMIN_ID):
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
    if not t or (t["user_id"] != cb.from_user.id and cb.from_user.id != ADMIN_ID):
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
    b.adjust(2, 1)
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
    await msg.answer("📝 Bio yozing (buyum haqida) yoki o'tkazib yuboring:", reply_markup=skip_cancel_kb())
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
    try:
        cap = f"🛍 Yangi sotuv #{short_id(sid)}\n👤 @{esc_md(uname)}\n📦 {esc_md(d['s_name'])}\n📝 {esc_md(bio or '-')}\n💰 {int(txt):,} {d['s_currency']}"
        if d.get("s_photo"):
            await bot.send_photo(ADMIN_ID, d["s_photo"], caption=cap)
        else:
            await bot.send_message(ADMIN_ID, cap)
    except Exception:
        pass
    await msg.answer(
        f"✅ Sotuv e'lon qilindi! *#{short_id(sid)}*\n📦 {d['s_name']}\n💰 {int(txt):,} {d['s_currency']}",
        reply_markup=main_kb()
    )

@dp.callback_query(F.data.startswith("esale_"))
async def cb_esale(cb: types.CallbackQuery, state: FSMContext):
    sid = cb.data.split("_")[1]
    s   = await get_sale(sid)
    if not s or (s["user_id"] != cb.from_user.id and cb.from_user.id != ADMIN_ID):
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
    if not s or (s["user_id"] != cb.from_user.id and cb.from_user.id != ADMIN_ID):
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
    try:
        if photo:
            await bot.send_photo(ADMIN_ID, photo, caption=text)
        else:
            await bot.send_message(ADMIN_ID, text)
    except Exception:
        pass
    await state.clear()
    await msg.answer("✅ Xabaringiz @notalonet ga yuborildi! Tez orada javob beriladi.", reply_markup=main_kb())

# ═══════════════════════════════════════════════════════
# ADMINLIK XIZMATI
# ═══════════════════════════════════════════════════════
@dp.message(F.text == "🛡 Adminlik xizmati")
async def cmd_admin_service(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    b = InlineKeyboardBuilder()
    b.button(text="📩 Adminga yozish", url=f"https://t.me/notalonet")
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
    if msg.text == "⏭ O'tkazib yuborish":
        await msg.answer("✍️ Taklifingizni yozing:", reply_markup=cancel_kb())
        await state.set_state(SuggestBot.message)
        return
    # Matn ham kiritilgan bo'lsa to'g'ridan yuborib yuboramiz
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
    try:
        if photo:
            await bot.send_photo(ADMIN_ID, photo, caption=text)
        else:
            await bot.send_message(ADMIN_ID, text)
    except Exception:
        pass
    await state.clear()
    await msg.answer(
        "✅ *Rahmat! Fikringiz e'tiborsiz qolmaydi* 🙏\n\n"
        "Taklifingiz adminimizga yuborildi!",
        reply_markup=main_kb()
    )

# ═══════════════════════════════════════════════════════
# REKLAMA QILISH
# ═══════════════════════════════════════════════════════
AD_PRICE = 5000  # so'm

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
    # Balansdan ayirish
    bal = await get_balance(uid)
    if bal < AD_PRICE:
        await state.clear()
        await msg.answer("❌ Hisobingiz yetarli emas!", reply_markup=main_kb())
        return
    await sub_balance(uid, AD_PRICE)
    await state.clear()
    # Hammaga yuborish
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
    # Adminga ham xabar
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📣 *Yangi reklama*\n\n"
            f"👤 @{esc_md(uname)} (`{uid}`)\n"
            f"💰 To'langan: {AD_PRICE:,} so'm\n"
            f"📤 Yuborildi: {sent}/{len(uids)} ta foydalanuvchiga"
        )
    except Exception:
        pass
    await msg.answer(
        f"✅ Reklamangiz *{sent}* ta foydalanuvchiga yuborildi!\n"
        f"💰 Hisobingizdan {AD_PRICE:,} so'm yechildi.",
        reply_markup=main_kb()
    )

# ═══════════════════════════════════════════════════════
# AUTOXABAR BO'LIMI  (Telethon MTProto orqali)
# ═══════════════════════════════════════════════════════
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError, PhoneCodeInvalidError,
    PhoneCodeExpiredError, FloodWaitError
)
from telethon.tl.types import Channel, Chat

TELEGRAM_API_ID   = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")

# Xotirada saqlanadigan vaqtinchalik Telethon clientlar (login jarayoni uchun)
_tl_clients: dict[int, TelegramClient] = {}

# ─── MongoDB yordamchilar ───────────────────────────────
async def ax_get(uid: int) -> dict:
    doc = await autoxabar_db.find_one({"user_id": uid})
    if not doc:
        doc = {
            "user_id": uid,
            "session": None,       # Telethon StringSession
            "photo":   None,
            "text":    None,
            "running": False,
            "interval": 5,
            "groups":  [],         # tanlangan guruh IDlari
        }
        await autoxabar_db.insert_one(doc)
    return doc

async def ax_set(uid: int, **kwargs):
    await autoxabar_db.update_one({"user_id": uid}, {"$set": kwargs}, upsert=True)

# ─── Telethon client olish ─────────────────────────────
async def _tl_get_client(uid: int) -> TelegramClient | None:
    """Saqlangan session bilan client qaytaradi (login bo'lgan bo'lsa)."""
    doc = await ax_get(uid)
    session_str = doc.get("session")
    if not session_str:
        return None
    client = TelegramClient(StringSession(session_str), TELEGRAM_API_ID, TELEGRAM_API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return None
    except Exception:
        return None
    return client

# ─── Xabar yuborish sikli ──────────────────────────────
_ax_tasks: dict[int, asyncio.Task] = {}

async def _ax_sender(uid: int):
    while True:
        doc = await ax_get(uid)
        if not doc.get("running"):
            break
        interval = doc.get("interval", 5) * 60
        groups   = doc.get("groups", [])
        photo    = doc.get("photo")
        text     = doc.get("text", "")
        client   = await _tl_get_client(uid)
        if client:
            for chat_id in groups:
                try:
                    if photo:
                        # Bot file_id dan faylni yuklab Telethon orqali yuborish
                        tg_file = await bot.get_file(photo)
                        file_bytes = await bot.download_file(tg_file.file_path)
                        await client.send_file(chat_id, file_bytes, caption=text)
                    else:
                        await client.send_message(chat_id, text)
                except FloodWaitError as e:
                    logging.warning(f"FloodWait {e.seconds}s uid={uid}")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logging.warning(f"Autoxabar xato ({chat_id}): {e}")
                await asyncio.sleep(2)
            await client.disconnect()
        else:
            logging.warning(f"uid={uid} session topilmadi, autoxabar to'xtatildi")
            await ax_set(uid, running=False)
            break
        await asyncio.sleep(interval)

def _ax_start_task(uid: int):
    if uid in _ax_tasks and not _ax_tasks[uid].done():
        return
    _ax_tasks[uid] = asyncio.create_task(_ax_sender(uid))

def _ax_stop_task(uid: int):
    if uid in _ax_tasks:
        _ax_tasks[uid].cancel()
        del _ax_tasks[uid]

# ─── Klaviaturalar ─────────────────────────────────────
def ax_main_kb():
    b = InlineKeyboardBuilder()
    b.button(text="✏️ Reklama yozish",            callback_data="ax_write")
    b.button(text="▶️ Xabar yuborishni boshlash",  callback_data="ax_toggle")
    b.button(text="👥 Guruhlar",                    callback_data="ax_groups")
    b.button(text="⏱ Vaqtni sozlash",               callback_data="ax_time")
    b.adjust(1)
    return b.as_markup()

def ax_time_kb(current: int):
    b = InlineKeyboardBuilder()
    for m in [5, 4, 3, 2, 1]:
        mark = "✅ " if m == current else ""
        b.button(text=f"{mark}{m} daqiqa", callback_data=f"axtime_{m}")
    b.button(text="🔢 Boshqa vaqt", callback_data="axtime_custom")
    b.button(text="🔙 Orqaga",      callback_data="ax_back")
    b.adjust(1)
    return b.as_markup()

def ax_groups_kb(groups_list: list, selected: list):
    b = InlineKeyboardBuilder()
    for g in groups_list:
        gid   = g["id"]
        gname = g.get("title", str(gid))[:30]
        mark  = "✅ " if gid in selected else "❌ "
        # Manfiy IDlar uchun 'n' prefiksi: -100123 -> axgrp_n100123
        safe_id = str(gid).replace("-", "n")
        b.button(text=f"{mark}{gname}", callback_data=f"axgrp_{safe_id}")
    b.button(text="🔙 Orqaga", callback_data="ax_back")
    b.adjust(1)
    return b.as_markup()

# ─── Umumiy menu ko'rsatish ────────────────────────────
async def _ax_show_menu(target, uid: int, edit=False):
    doc = await ax_get(uid)
    logged_in    = bool(doc.get("session"))
    status       = "▶️ Ishlamoqda" if doc.get("running") else "⏹ To'xtatilgan"
    reklama      = doc.get("text") or "Yo'q"
    interval     = doc.get("interval", 5)
    groups_count = len(doc.get("groups", []))
    auth_line    = "✅ Kirgan" if logged_in else "❌ Kirilmagan"
    text = (
        f"📢 *Autoxabar*\n\n"
        f"🔐 Akkaunt: *{auth_line}*\n"
        f"📊 Holat: *{status}*\n"
        f"⏱ Interval: *{interval} daqiqa*\n"
        f"👥 Guruhlar: *{groups_count} ta*\n"
        f"📝 Reklama: _{esc_md(reklama[:50])}{'...' if len(reklama)>50 else ''}_\n\n"
        f"Bo'limni tanlang:"
    )
    kb = ax_main_kb()
    if edit:
        try:
            if target.message.photo:
                await target.message.delete()
                await target.message.answer(text, reply_markup=kb)
            else:
                await target.message.edit_text(text, reply_markup=kb)
        except Exception:
            try:
                await target.message.answer(text, reply_markup=kb)
            except Exception:
                pass
    else:
        await target.answer(text, reply_markup=kb)

# ─── Autoxabar kirish (📢 Autoxabar tugmasi) ──────────
@dp.message(F.text == "📢 Autoxabar")
async def cmd_autoxabar(msg: types.Message, state: FSMContext):
    if not await check_access(msg, state):
        return
    await state.clear()
    uid = msg.from_user.id
    doc = await ax_get(uid)
    # Login bo'lmagan bo'lsa — avval login
    if not doc.get("session"):
        await _ax_ask_phone(msg, state)
        return
    # Login bo'lgan — clientni tekshir
    client = await _tl_get_client(uid)
    if not client:
        await ax_set(uid, session=None)
        await _ax_ask_phone(msg, state)
        return
    await client.disconnect()
    await _ax_show_menu(msg, uid)

# ─── Login oqimi ───────────────────────────────────────
async def _ax_ask_phone(msg: types.Message, state: FSMContext):
    await msg.answer(
        "📱 *Autoxabar — Kirish*\n\n"
        "Telegram akkauntingizga kirish uchun telefon raqamingizni yuboring.\n"
        "_(Xalqaro format: +998901234567)_",
        reply_markup=cancel_kb()
    )
    await state.set_state(AutoxabarFlow.login_phone)

@dp.message(AutoxabarFlow.login_phone)
async def ax_login_phone(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    phone = msg.text.strip()
    uid   = msg.from_user.id
    client = TelegramClient(StringSession(), TELEGRAM_API_ID, TELEGRAM_API_HASH)
    try:
        await client.connect()
        sent = await client.send_code_request(phone)
        _tl_clients[uid] = client
        await state.update_data(ax_phone=phone, ax_phone_hash=sent.phone_code_hash)
        await msg.answer(
            f"📩 *Kod yuborildi!*\n\n"
            f"`{phone}` raqamiga Telegram kodi keldi.\n"
            f"Kodni yuboring:",
            reply_markup=cancel_kb()
        )
        await state.set_state(AutoxabarFlow.login_code)
    except FloodWaitError as e:
        await client.disconnect()
        await msg.answer(f"⏳ Juda ko'p urinish. {e.seconds} soniya kuting.")
        await state.clear()
    except Exception as e:
        await client.disconnect()
        await msg.answer(f"❌ Xato: {e}\n\nRaqamni to'g'ri kiriting:")

@dp.message(AutoxabarFlow.login_code)
async def ax_login_code(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        uid = msg.from_user.id
        c   = _tl_clients.pop(uid, None)
        if c:
            await c.disconnect()
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    uid   = msg.from_user.id
    code  = msg.text.strip().replace(" ", "")
    d     = await state.get_data()
    phone = d.get("ax_phone")
    phone_hash = d.get("ax_phone_hash")
    client = _tl_clients.get(uid)
    if not client:
        await state.clear()
        await msg.answer("❌ Session tugadi. Qaytadan boshlang.", reply_markup=main_kb())
        return
    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_hash)
        session_str = client.session.save()
        await client.disconnect()
        _tl_clients.pop(uid, None)
        await ax_set(uid, session=session_str)
        await state.clear()
        await msg.answer(
            "✅ *Muvaffaqiyatli kirdingiz!*\n\nEndi autoxabar bo'limidan foydalanishingiz mumkin.",
            reply_markup=main_kb()
        )
        await _ax_show_menu(msg, uid)
    except SessionPasswordNeededError:
        await state.set_state(AutoxabarFlow.login_2fa)
        await msg.answer(
            "🔐 *2FA parol kerak*\n\nTelegram parolingizni yuboring:",
            reply_markup=cancel_kb()
        )
    except (PhoneCodeInvalidError, PhoneCodeExpiredError):
        await msg.answer("❌ Kod noto'g'ri yoki muddati o'tgan. Qayta yuboring:")
    except Exception as e:
        await msg.answer(f"❌ Xato: {e}")

@dp.message(AutoxabarFlow.login_2fa)
async def ax_login_2fa(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        uid = msg.from_user.id
        c   = _tl_clients.pop(uid, None)
        if c:
            await c.disconnect()
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    uid      = msg.from_user.id
    password = msg.text.strip()
    client   = _tl_clients.get(uid)
    if not client:
        await state.clear()
        await msg.answer("❌ Session tugadi. Qaytadan boshlang.", reply_markup=main_kb())
        return
    try:
        await client.sign_in(password=password)
        session_str = client.session.save()
        await client.disconnect()
        _tl_clients.pop(uid, None)
        await ax_set(uid, session=session_str)
        await state.clear()
        await msg.answer(
            "✅ *Muvaffaqiyatli kirdingiz!*",
            reply_markup=main_kb()
        )
        await _ax_show_menu(msg, uid)
    except Exception as e:
        await msg.answer(f"❌ Parol noto'g'ri: {e}")

# ─── Orqaga tugmasi ────────────────────────────────────
@dp.callback_query(F.data == "ax_back")
async def ax_back(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await _ax_show_menu(cb, cb.from_user.id, edit=True)
    await cb.answer()

# ─── 1-bo'lim: Reklama yozish ─────────────────────────
@dp.callback_query(F.data == "ax_write")
async def ax_write(cb: types.CallbackQuery, state: FSMContext):
    # Har qanday xabar turida ishlaydi (photo yoki text)
    await cb.message.answer(
        "📸 *Reklama rasmi*\n\nRasm yuboring yoki o'tkazib yuboring (rasmsiz ham bo'ladi):",
        reply_markup=skip_cancel_kb()
    )
    await state.set_state(AutoxabarFlow.photo)
    await cb.answer()

@dp.message(AutoxabarFlow.photo, F.photo)
async def ax_photo_recv(msg: types.Message, state: FSMContext):
    await state.update_data(ax_photo=msg.photo[-1].file_id)
    await msg.answer("📝 Reklama matnini yozing:", reply_markup=cancel_kb())
    await state.set_state(AutoxabarFlow.text)

@dp.message(AutoxabarFlow.photo)
async def ax_photo_skip(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    if msg.text == "⏭ O'tkazib yuborish":
        await state.update_data(ax_photo=None)
        await msg.answer("📝 Reklama matnini yozing:", reply_markup=cancel_kb())
        await state.set_state(AutoxabarFlow.text)
        return
    await msg.answer("❌ Rasm yuboring yoki O'tkazib yuborish tugmasini bosing:")

@dp.message(AutoxabarFlow.text)
async def ax_text_recv(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    uid   = msg.from_user.id
    d     = await state.get_data()
    photo = d.get("ax_photo")
    text  = msg.text.strip()
    await ax_set(uid, photo=photo, text=text)
    await state.clear()
    b = InlineKeyboardBuilder()
    b.button(text="✏️ Tahrirlash", callback_data="ax_write")
    b.button(text="🔙 Orqaga",     callback_data="ax_back")
    b.adjust(1)
    preview = f"📣 *Reklama saqlandi!*\n\n📝 Matn: _{esc_md(text[:100])}_"
    # Har doim yangi xabar sifatida jo'natamiz (photo bilan ham, rasmsiz ham)
    if photo:
        await msg.answer_photo(photo, caption=preview, reply_markup=b.as_markup())
    else:
        await msg.answer(preview, reply_markup=b.as_markup())
    # Asosiy klaviaturani tiklash
    await msg.answer("👆 Yuqoridagi tugmalardan foydalaning.", reply_markup=main_kb())

# ─── 2-bo'lim: Boshlash/To'xtatish ───────────────────
@dp.callback_query(F.data == "ax_toggle")
async def ax_toggle(cb: types.CallbackQuery):
    uid = cb.from_user.id
    doc = await ax_get(uid)
    if not doc.get("text"):
        await cb.answer("❌ Avval reklama yozing! (1-bo'lim)", show_alert=True)
        return
    if not doc.get("groups"):
        await cb.answer("❌ Avval guruhlarni tanlang! (3-bo'lim)", show_alert=True)
        return
    if not doc.get("session"):
        await cb.answer("❌ Avval akkauntga kiring!", show_alert=True)
        return
    running = doc.get("running", False)
    if running:
        await ax_set(uid, running=False)
        _ax_stop_task(uid)
        await cb.answer("⏹ Autoxabar to'xtatildi!", show_alert=True)
    else:
        await ax_set(uid, running=True)
        _ax_start_task(uid)
        await cb.answer("▶️ Autoxabar boshlandi!", show_alert=True)
    await _ax_show_menu(cb, uid, edit=True)

# ─── 3-bo'lim: Guruhlar (Telethon orqali) ─────────────
@dp.callback_query(F.data == "ax_groups")
async def ax_groups(cb: types.CallbackQuery):
    uid    = cb.from_user.id
    doc    = await ax_get(uid)
    if not doc.get("session"):
        await cb.answer("❌ Avval akkauntga kiring!", show_alert=True)
        return
    await cb.answer("⏳ Guruhlar yuklanmoqda...")
    client = await _tl_get_client(uid)
    if not client:
        await ax_set(uid, session=None)
        await cb.message.answer("❌ Session yaroqsiz. Qaytadan /start bosing va Autoxabar ni tanlang.")
        return
    try:
        groups_list = []
        async for dialog in client.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                groups_list.append({
                    "id":    dialog.id,
                    "title": dialog.title or str(dialog.id)
                })
        await client.disconnect()
        await ax_set(uid, all_groups=groups_list)
        selected = doc.get("groups", [])
        if not groups_list:
            await cb.message.answer("❌ Siz hech qanday guruh/kanalda yo'q ekansiz.")
            return
        await cb.message.edit_text(
            f"👥 *Guruhlar va Kanallar*\n\n"
            f"✅ tanlangan | ❌ tanlanmagan\n"
            f"Jami: {len(groups_list)} ta | Tanlangan: {len(selected)} ta\n\n"
            f"Xabar yuborilsin bo'lganini tanlang:",
            reply_markup=ax_groups_kb(groups_list, selected)
        )
    except Exception as e:
        await cb.message.answer(f"❌ Xato: {e}")

@dp.callback_query(F.data.startswith("axgrp_"))
async def ax_group_toggle(cb: types.CallbackQuery):
    uid  = cb.from_user.id
    # callback_data: axgrp_<safe_id>  — manfiy IDlar 'n' bilan: n100123 = -100123
    raw  = cb.data[len("axgrp_"):]
    gid  = int(raw.replace("n", "-")) if raw.startswith("n") else int(raw)
    doc  = await ax_get(uid)
    sel  = list(doc.get("groups", []))
    if gid in sel:
        sel.remove(gid)
    else:
        sel.append(gid)
    await ax_set(uid, groups=sel)
    doc        = await ax_get(uid)
    all_groups = doc.get("all_groups", [])
    selected   = doc.get("groups", [])
    try:
        await cb.message.edit_text(
            f"👥 *Guruhlar va Kanallar*\n\n"
            f"✅ tanlangan | ❌ tanlanmagan\n"
            f"Jami: {len(all_groups)} ta | Tanlangan: {len(selected)} ta\n\n"
            f"Xabar yuborilsin bo'lganini tanlang:",
            reply_markup=ax_groups_kb(all_groups, selected)
        )
    except Exception:
        pass
    await cb.answer()

# ─── 4-bo'lim: Vaqt sozlash ───────────────────────────
@dp.callback_query(F.data == "ax_time")
async def ax_time(cb: types.CallbackQuery):
    uid = cb.from_user.id
    doc = await ax_get(uid)
    cur = doc.get("interval", 5)
    await cb.message.edit_text(
        f"⏱ *Vaqtni sozlash*\n\nHozirgi interval: *{cur} daqiqa*\n\nHar necha daqiqada yuborilsin?",
        reply_markup=ax_time_kb(cur)
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("axtime_"))
async def ax_time_set(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    val = cb.data.split("_")[1]
    if val == "custom":
        await cb.message.answer(
            "🔢 1 dan 1000 gacha daqiqa kiriting:",
            reply_markup=cancel_kb()
        )
        await state.set_state(AutoxabarFlow.confirm_edit)
        await cb.answer()
        return
    minutes = int(val)
    await ax_set(uid, interval=minutes)
    doc = await ax_get(uid)
    cur = doc.get("interval", 5)
    try:
        await cb.message.edit_text(
            f"⏱ *Vaqtni sozlash*\n\nHozirgi interval: *{cur} daqiqa*\n\nHar necha daqiqada yuborilsin?",
            reply_markup=ax_time_kb(cur)
        )
    except Exception:
        pass
    await cb.answer(f"✅ {minutes} daqiqaga o'rnatildi!")

@dp.message(AutoxabarFlow.confirm_edit)
async def ax_custom_time(msg: types.Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    txt = msg.text.strip()
    if not txt.isdigit() or not (1 <= int(txt) <= 1000):
        await msg.answer("❌ 1 dan 1000 gacha son kiriting:")
        return
    uid     = msg.from_user.id
    minutes = int(txt)
    await ax_set(uid, interval=minutes)
    await state.clear()
    b = InlineKeyboardBuilder()
    b.button(text="🔙 Orqaga", callback_data="ax_back")
    await msg.answer(f"✅ Interval *{minutes} daqiqa* ga o'rnatildi!", reply_markup=b.as_markup())

# ═══════════════════════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════════════════════
@dp.message(Command("admin"))
async def cmd_admin(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("❌ Ruxsat yo'q!")
        return
    tr   = await active_trades()
    sl   = await active_sales()
    or_  = await pending_orders()
    cnt  = await users_count()
    b    = InlineKeyboardBuilder()
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
    if cb.from_user.id != ADMIN_ID:
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
    if cb.from_user.id != ADMIN_ID:
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
    if cb.from_user.id != ADMIN_ID:
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
    if cb.from_user.id != ADMIN_ID:
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
    if msg.from_user.id != ADMIN_ID:
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
    if cb.from_user.id != ADMIN_ID:
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
WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL", "")   # Render avtomatik beradi
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL  = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
WEB_PORT     = int(os.getenv("PORT", 10000))           # Render PORT env beradi


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

    # Health-check endpoint — Render shu URL ni so'raydi
    async def health(request):
        return web.Response(text="OK")

    app.router.add_get("/", health)

    # aiogram webhook handler
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    logging.info(f"🚀 Server port {WEB_PORT} da ishga tushdi")
    web.run_app(app, host="0.0.0.0", port=WEB_PORT)


if __name__ == "__main__":
    main()
