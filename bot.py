import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import config
import database as db

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Клавиатуры
contact_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]],
    resize_keyboard=True
)

CITIES = ["Владивосток", "Уссурийск", "Находка", "Хабаровск"]

def get_cities_keyboard():
    keyboard = []
    row = []
    for i, city in enumerate(CITIES):
        row.append(KeyboardButton(text=city))
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_main_menu():
    keyboard = [
        [KeyboardButton(text="📦 Отправить груз"), KeyboardButton(text="🚚 Я водитель")],
        [KeyboardButton(text="⭐ Мой рейтинг"), KeyboardButton(text="📞 Поддержка")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_driver_menu():
    keyboard = [
        [KeyboardButton(text="🔍 Искать груз"), KeyboardButton(text="📍 Фильтр по городам")],
        [KeyboardButton(text="⭐ Мой рейтинг"), KeyboardButton(text="📞 Поддержка")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

class CargoStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_from_city = State()
    waiting_for_to_city = State()
    waiting_for_weight = State()
    waiting_for_volume = State()
    waiting_for_description = State()
    waiting_for_photo = State()
    filter_from_city = State()
    filter_to_city = State()

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    if not db.is_user_verified(user_id):
        await message.answer(
            "🔐 Добро пожаловать в сервис попутных грузоперевозок!\n\n"
            "Мы работаем по направлениям:\n"
            "• Владивосток ↔ Уссурийск\n"
            "• Владивосток ↔ Находка\n"
            "• Владивосток ↔ Хабаровск\n\n"
            "Для начала работы необходимо подтвердить номер телефона.",
            reply_markup=contact_keyboard
        )
        await state.set_state(CargoStates.waiting_for_phone)
        return
    
    await message.answer("Главное меню:", reply_markup=get_main_menu())

@dp.message(F.contact, CargoStates.waiting_for_phone)
async def handle_contact(message: types.Message, state: FSMContext):
    if message.contact.user_id != message.from_user.id:
        await message.answer("❌ Пожалуйста, отправьте свой номер телефона.", reply_markup=contact_keyboard)
        return
    
    phone = message.contact.phone_number
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    
    db.save_user(user_id, phone, full_name)
    
    await message.answer("✅ Номер подтверждён!", reply_markup=ReplyKeyboardRemove())
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_menu())

@dp.message(F.text == "📦 Отправить груз")
async def send_cargo_start(message: types.Message, state: FSMContext):
    await message.answer("Выберите город отправления:", reply_markup=get_cities_keyboard())
    await state.set_state(CargoStates.waiting_for_from_city)

@dp.message(CargoStates.waiting_for_from_city)
async def process_from_city(message: types.Message, state: FSMContext):
    if message.text not in CITIES:
        await message.answer("Пожалуйста, выберите город из списка кнопок.")
        return
    
    await state.update_data(from_city=message.text)
    await message.answer("Выберите город назначения:", reply_markup=get_cities_keyboard())
    await state.set_state(CargoStates.waiting_for_to_city)

@dp.message(CargoStates.waiting_for_to_city)
async def process_to_city(message: types.Message, state: FSMContext):
    if message.text not in CITIES:
        await message.answer("Пожалуйста, выберите город из списка кнопок.")
        return
    
    data = await state.get_data()
    if message.text == data['from_city']:
        await message.answer("Города отправления и назначения не могут совпадать. Выберите другой город:")
        return
    
    await state.update_data(to_city=message.text)
    await message.answer("📸 Загрузите фото груза:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CargoStates.waiting_for_photo)

@dp.message(CargoStates.waiting_for_photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    photo = message.photo[-1]
    await state.update_data(photo_file_id=photo.file_id)
    
    await message.answer("⚖️ Укажите вес груза (в кг):")
    await state.set_state(CargoStates.waiting_for_weight)

@dp.message(CargoStates.waiting_for_weight)
async def process_weight(message: types.Message, state: FSMContext):
    try:
        weight = float(message.text)
        if weight <= 0:
            raise ValueError
        await state.update_data(weight=weight)
        await message.answer("📦 Укажите объём груза (в м³):")
        await state.set_state(CargoStates.waiting_for_volume)
    except ValueError:
        await message.answer("Пожалуйста, введите число больше 0")

@dp.message(CargoStates.waiting_for_volume)
async def process_volume(message: types.Message, state: FSMContext):
    try:
        volume = float(message.text)
        if volume < 0:
            raise ValueError
        await state.update_data(volume=volume)
        await message.answer("📝 Опишите груз подробнее:")
        await state.set_state(CargoStates.waiting_for_description)
    except ValueError:
        await message.answer("Пожалуйста, введите число")

@dp.message(CargoStates.waiting_for_description)
async def process_description(message: types.Message, state: FSMContext):
    description = message.text
    await state.update_data(description=description)
    
    data = await state.get_data()
    
    ad_id = db.save_cargo_ad(
        user_id=message.from_user.id,
        from_city=data['from_city'],
        to_city=data['to_city'],
        weight=data['weight'],
        volume=data['volume'],
        description=description,
        photo_file_id=data['photo_file_id']
    )
    
    await message.answer_photo(
        photo=data['photo_file_id'],
        caption=f"✅ Заявка #{ad_id} создана!\n"
                f"📍 {data['from_city']} → {data['to_city']}\n"
                f"⚖️ {data['weight']} кг\n"
                f"📦 {data['volume']} м³\n"
                f"📝 {description}"
    )
    
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_menu())

@dp.message(F.text == "🚚 Я водитель")
async def switch_to_driver(message: types.Message):
    await message.answer("Режим водителя:", reply_markup=get_driver_menu())

@dp.message(F.text == "🔍 Искать груз")
async def search_cargo(message: types.Message):
    ads = db.get_active_ads()
    
    if not ads:
        await message.answer("🔍 Пока нет активных заявок.")
        return
    
    for ad in ads[:5]:
        ad_id, user_id, from_city, to_city, weight, volume, description, photo_file_id, created_at = ad
        await message.answer_photo(
            photo=photo_file_id,
            caption=f"📦 Заявка #{ad_id}\n📍 {from_city} → {to_city}\n⚖️ {weight} кг\n📦 {volume} м³\n📝 {description}"
        )

@dp.message(F.text == "📍 Фильтр по городам")
async def filter_start(message: types.Message, state: FSMContext):
    await message.answer("Выберите город отправления:", reply_markup=get_cities_keyboard())
    await state.set_state(CargoStates.filter_from_city)

@dp.message(CargoStates.filter_from_city)
async def filter_from_city(message: types.Message, state: FSMContext):
    if message.text not in CITIES:
        await message.answer("Пожалуйста, выберите город из списка.")
        return
    
    await state.update_data(filter_from=message.text)
    await message.answer("Выберите город назначения:", reply_markup=get_cities_keyboard())
    await state.set_state(CargoStates.filter_to_city)

@dp.message(CargoStates.filter_to_city)
async def filter_to_city(message: types.Message, state: FSMContext):
    if message.text not in CITIES:
        await message.answer("Пожалуйста, выберите город из списка.")
        return
    
    data = await state.get_data()
    from_city = data['filter_from']
    to_city = message.text
    
    ads = db.get_active_ads(from_city, to_city)
    
    if not ads:
        await message.answer(f"🔍 По направлению {from_city} → {to_city} заявок не найдено.")
    else:
        await message.answer(f"🔍 Найдено заявок: {len(ads)}")
        for ad in ads[:5]:
            ad_id, user_id, f_city, t_city, weight, volume, description, photo_file_id, created_at = ad
            await message.answer_photo(
                photo=photo_file_id,
                caption=f"📦 Заявка #{ad_id}\n📍 {f_city} → {t_city}\n⚖️ {weight} кг\n📦 {volume} м³\n📝 {description}"
            )
    
    await state.clear()

@dp.message(F.text == "⭐ Мой рейтинг")
async def show_rating(message: types.Message):
    await message.answer("⭐ Рейтинг пока в разработке. Скоро появится!")

@dp.message(F.text == "📞 Поддержка")
async def support(message: types.Message):
    await message.answer("📞 По всем вопросам пишите: @your_support_username")
import asyncio
from aiohttp import web

async def handle(request):
    return web.Response(text="Bot is running")

async def run_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()

async def main():
    await asyncio.gather(
        dp.start_polling(bot),
        run_web_server()
    )

if __name__ == "__main__":
    db.init_db()
    print("Бот запущен...")
    asyncio.run(main())
if __name__ == "__main__":
    db.init_db()
    print("Бот запущен...")
    dp.run_polling(bot)
