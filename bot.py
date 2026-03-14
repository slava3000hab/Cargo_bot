import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiohttp import web
import config
import database as db

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==================== КЛАВИАТУРЫ ====================

# Клавиатура для запроса контакта
contact_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]],
    resize_keyboard=True
)

# Список доступных городов
CITIES = ["Владивосток", "Уссурийск", "Находка", "Хабаровск"]

def get_cities_keyboard():
    """Клавиатура для выбора города (по 2 кнопки в ряд)"""
    keyboard = []
    row = []
    for i, city in enumerate(CITIES):
        row.append(KeyboardButton(text=city))
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    if row:  # Если остались непарные кнопки
        keyboard.append(row)
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_main_menu():
    """Главное меню для отправителя"""
    keyboard = [
        [KeyboardButton(text="📦 Отправить груз"), KeyboardButton(text="🚚 Я водитель")],
        [KeyboardButton(text="⭐ Мой рейтинг"), KeyboardButton(text="📞 Поддержка")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_driver_menu():
    """Меню для водителя"""
    keyboard = [
        [KeyboardButton(text="🔍 Искать груз"), KeyboardButton(text="📍 Фильтр по городам")],
        [KeyboardButton(text="⭐ Мой рейтинг"), KeyboardButton(text="📞 Поддержка")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# ==================== СОСТОЯНИЯ FSM ====================

class CargoStates(StatesGroup):
    waiting_for_phone = State()          # Ожидание номера телефона
    waiting_for_from_city = State()      # Ожидание города отправления
    waiting_for_to_city = State()        # Ожидание города назначения
    waiting_for_photo = State()           # Ожидание фото груза
    waiting_for_weight = State()          # Ожидание веса
    waiting_for_volume = State()          # Ожидание объёма
    waiting_for_description = State()     # Ожидание описания
    filter_from_city = State()            # Фильтр: город отправления
    filter_to_city = State()              # Фильтр: город назначения

# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    """Обработка команды /start"""
    user_id = message.from_user.id
    
    # Проверяем, верифицирован ли пользователь
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
    """Обработка полученного контакта (номера телефона)"""
    # Проверяем, что пользователь отправил свой номер
    if message.contact.user_id != message.from_user.id:
        await message.answer(
            "❌ Пожалуйста, отправьте свой номер телефона, нажав на кнопку.",
            reply_markup=contact_keyboard
        )
        return
    
    # Сохраняем данные пользователя
    phone = message.contact.phone_number
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    
    db.save_user(user_id, phone, full_name)
    
    await message.answer(
        "✅ Номер подтверждён! Теперь вы можете пользоваться сервисом.",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_menu())

# ==================== СОЗДАНИЕ ЗАЯВКИ (ОТПРАВИТЕЛЬ) ====================

@dp.message(F.text == "📦 Отправить груз")
async def send_cargo_start(message: types.Message, state: FSMContext):
    """Начало создания заявки на груз"""
    await message.answer(
        "Выберите город отправления:",
        reply_markup=get_cities_keyboard()
    )
    await state.set_state(CargoStates.waiting_for_from_city)

@dp.message(CargoStates.waiting_for_from_city)
async def process_from_city(message: types.Message, state: FSMContext):
    """Обработка города отправления"""
    if message.text not in CITIES:
        await message.answer("Пожалуйста, выберите город из списка кнопок.")
        return
    
    await state.update_data(from_city=message.text)
    await message.answer(
        "Выберите город назначения:",
        reply_markup=get_cities_keyboard()
    )
    await state.set_state(CargoStates.waiting_for_to_city)

@dp.message(CargoStates.waiting_for_to_city)
async def process_to_city(message: types.Message, state: FSMContext):
    """Обработка города назначения"""
    if message.text not in CITIES:
        await message.answer("Пожалуйста, выберите город из списка кнопок.")
        return
    
    data = await state.get_data()
    if message.text == data['from_city']:
        await message.answer(
            "Города отправления и назначения не могут совпадать. Выберите другой город:",
            reply_markup=get_cities_keyboard()
        )
        return
    
    await state.update_data(to_city=message.text)
    await message.answer(
        "📸 Загрузите фото груза:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(CargoStates.waiting_for_photo)

@dp.message(CargoStates.waiting_for_photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    """Обработка загруженного фото"""
    # Берём самое большое фото (последнее в списке)
    photo = message.photo[-1]
    await state.update_data(photo_file_id=photo.file_id)
    
    await message.answer("⚖️ Укажите вес груза (в кг):")
    await state.set_state(CargoStates.waiting_for_weight)

@dp.message(CargoStates.waiting_for_weight)
async def process_weight(message: types.Message, state: FSMContext):
    """Обработка веса груза"""
    try:
        weight = float(message.text.replace(',', '.'))
        if weight <= 0:
            raise ValueError
        await state.update_data(weight=weight)
        await message.answer("📦 Укажите объём груза (в м³):")
        await state.set_state(CargoStates.waiting_for_volume)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число больше 0 (например: 50, 100.5)")

@dp.message(CargoStates.waiting_for_volume)
async def process_volume(message: types.Message, state: FSMContext):
    """Обработка объёма груза"""
    try:
        volume = float(message.text.replace(',', '.'))
        if volume < 0:
            raise ValueError
        await state.update_data(volume=volume)
        await message.answer("📝 Опишите груз подробнее (что это, есть ли особенности):")
        await state.set_state(CargoStates.waiting_for_description)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число (например: 1, 2.5)")

@dp.message(CargoStates.waiting_for_description)
async def process_description(message: types.Message, state: FSMContext):
    """Обработка описания и сохранение заявки"""
    description = message.text
    await state.update_data(description=description)
    
    # Получаем все данные
    data = await state.get_data()
    
    # Сохраняем заявку в базу
    ad_id = db.save_cargo_ad(
        user_id=message.from_user.id,
        from_city=data['from_city'],
        to_city=data['to_city'],
        weight=data['weight'],
        volume=data['volume'],
        description=description,
        photo_file_id=data['photo_file_id']
    )
    
    # Отправляем подтверждение с фото
    await message.answer_photo(
        photo=data['photo_file_id'],
        caption=f"✅ **Заявка #{ad_id} создана!**\n\n"
                f"📍 {data['from_city']} → {data['to_city']}\n"
                f"⚖️ Вес: {data['weight']} кг\n"
                f"📦 Объём: {data['volume']} м³\n"
                f"📝 {description}",
        parse_mode="Markdown"
    )
    
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_menu())

# ==================== РЕЖИМ ВОДИТЕЛЯ ====================

@dp.message(F.text == "🚚 Я водитель")
async def switch_to_driver(message: types.Message):
    """Переключение в режим водителя"""
    await message.answer(
        "🚚 **Режим водителя**\n\n"
        "Теперь вы можете искать доступные грузы.",
        reply_markup=get_driver_menu(),
        parse_mode="Markdown"
    )

@dp.message(F.text == "🔍 Искать груз")
async def search_cargo(message: types.Message):
    """Поиск всех грузов без фильтра"""
    ads = db.get_active_ads()
    
    if not ads:
        await message.answer("🔍 Пока нет активных заявок на грузоперевозку.")
        return
    
    await message.answer(f"🔍 **Найдено заявок: {len(ads)}**\nПоказываю последние:", parse_mode="Markdown")
    
    for ad in ads[:5]:
        ad_id, user_id, from_city, to_city, weight, volume, description, photo_file_id, created_at = ad
        
        # Получаем username отправителя
        sender_username = db.get_user_username(user_id)
        
        # Формируем текст с кликабельным username
        ad_text = (
            f"📦 **Заявка #{ad_id}**\n"
            f"📍 {from_city} → {to_city}\n"
            f"⚖️ {weight} кг, 📦 {volume} м³\n"
            f"📝 {description}\n"
            f"🕐 {created_at[:16]}\n\n"
            f"👤 **Отправитель:** {sender_username}\n"
            f"💬 Нажмите на username выше чтобы написать"
        )
        
        try:
            await message.answer_photo(
                photo=photo_file_id,
                caption=ad_text,
                parse_mode="Markdown"
            )
        except Exception:
            await message.answer(ad_text, parse_mode="Markdown")

@dp.message(F.text == "📍 Фильтр по городам")
async def filter_start(message: types.Message, state: FSMContext):
    """Начало фильтрации по городам"""
    await message.answer(
        "Выберите **город отправления** для фильтрации:",
        reply_markup=get_cities_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(CargoStates.filter_from_city)

@dp.message(CargoStates.filter_from_city)
async def filter_from_city(message: types.Message, state: FSMContext):
    """Выбор города отправления для фильтра"""
    if message.text not in CITIES:
        await message.answer("Пожалуйста, выберите город из списка кнопок.")
        return
    
    await state.update_data(filter_from=message.text)
    await message.answer(
        "Выберите **город назначения** для фильтрации:",
        reply_markup=get_cities_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(CargoStates.filter_to_city)

@dp.message(CargoStates.filter_to_city)
async def filter_to_city(message: types.Message, state: FSMContext):
    """Применение фильтра по городам"""
    if message.text not in CITIES:
        await message.answer("Пожалуйста, выберите город из списка кнопок.")
        return
    
    data = await state.get_data()
    from_city = data['filter_from']
    to_city = message.text
    
    ads = db.get_active_ads(from_city, to_city)
    
    if not ads:
        await message.answer(f"🔍 По направлению {from_city} → {to_city} заявок не найдено.")
    else:
        await message.answer(f"🔍 **Найдено заявок: {len(ads)}** по направлению {from_city} → {to_city}", parse_mode="Markdown")
        
        for ad in ads[:5]:
            ad_id, user_id, f_city, t_city, weight, volume, description, photo_file_id, created_at = ad
            
            # Получаем username отправителя
            sender_username = db.get_user_username(user_id)
            
            ad_text = (
                f"📦 **Заявка #{ad_id}**\n"
                f"📍 {f_city} → {t_city}\n"
                f"⚖️ {weight} кг, 📦 {volume} м³\n"
                f"📝 {description}\n"
                f"🕐 {created_at[:16]}\n\n"
                f"👤 **Отправитель:** {sender_username}\n"
                f"💬 Нажмите на username выше чтобы написать"
            )
            
            try:
                await message.answer_photo(
                    photo=photo_file_id,
                    caption=ad_text,
                    parse_mode="Markdown"
                )
            except:
                await message.answer(ad_text, parse_mode="Markdown")
    
    await state.clear()

# ==================== ДОПОЛНИТЕЛЬНЫЕ КОМАНДЫ ====================

@dp.message(F.text == "⭐ Мой рейтинг")
async def show_rating(message: types.Message):
    """Показать рейтинг пользователя"""
    # Здесь можно добавить логику подсчёта рейтинга из базы
    await message.answer(
        "⭐ **Ваш рейтинг:** 0 (пока нет отзывов)\n\n"
        "Рейтинг формируется на основе отзывов после завершённых поездок.\n"
        "Эта функция будет добавлена в ближайшее время!",
        parse_mode="Markdown"
    )

@dp.message(F.text == "📞 Поддержка")
async def support(message: types.Message):
    """Поддержка"""
    await message.answer(
        "📞 **Поддержка**\n\n"
        "По всем вопросам пишите: @Miaov3\n"
        "Время ответа: обычно в течение часа.",
        parse_mode="Markdown"
    )

@dp.message()
async def handle_unknown(message: types.Message):
    """Обработка неизвестных команд"""
    await message.answer(
        "Я не понял команду. Используйте кнопки меню или напишите /start",
        reply_markup=get_main_menu()
    )

# ==================== ВЕБ-СЕРВЕР ДЛЯ RENDER ====================

async def handle_http(request):
    """Обработчик HTTP-запросов для проверки статуса"""
    return web.Response(text="Бот работает! 🤖")

async def run_web_server():
    """Запуск веб-сервера для Render"""
    app = web.Application()
    app.router.add_get('/', handle_http)
    app.router.add_get('/health', handle_http)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Render ожидает порт 10000
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    print("🌐 Веб-сервер запущен на порту 10000")

async def main():
    """Главная функция, запускающая и бота, и веб-сервер"""
    # Запускаем обе задачи одновременно
    await asyncio.gather(
        dp.start_polling(bot),
        run_web_server()
    )

# ==================== ТОЧКА ВХОДА ====================

if __name__ == "__main__":
    # Инициализируем базу данных
    db.init_db()
    print("🚀 Бот запущен...")
    
    try:
        # Запускаем асинхронную главную функцию
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Бот остановлен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
