import logging
import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiohttp import web
import config
import database as db

# ==================== НАСТРОЙКИ ЛОГИРОВАНИЯ ====================
logging.basicConfig(level=logging.INFO)

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==================== РЕГИОНЫ И ГОРОДА ====================
REGIONS = {
    "Хабаровский край": [
        "Хабаровск", "Комсомольск-на-Амуре", "Амурск",
        "Советская Гавань", "Николаевск-на-Амуре", "Бикин", "Вяземский"
    ],
    "Приморский край": [
        "Владивосток", "Уссурийск", "Находка", "Артём",
        "Большой Камень", "Партизанск", "Лесозаводск", "Дальнегорск",
        "Спасск-Дальний", "Арсеньев", "Фокино", "Дальнереченск",
        "Лучегорск", "Кавалерово"
    ]
}

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ КЛАВИАТУР ====================

def get_regions_keyboard():
    """Клавиатура со списком регионов"""
    keyboard = [[KeyboardButton(text=region)] for region in REGIONS.keys()]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_cities_keyboard(region):
    """Клавиатура с городами выбранного региона (по 2 в ряд)"""
    cities = REGIONS.get(region, [])
    keyboard = []
    row = []
    for i, city in enumerate(cities):
        row.append(KeyboardButton(text=city))
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    # Кнопка возврата к выбору региона
    keyboard.append([KeyboardButton(text="🔙 Назад к регионам")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_cities_keyboard_with_any(region):
    """Клавиатура для фильтрации: города + 'Любой' + 'Назад'"""
    cities = REGIONS.get(region, [])
    keyboard = []
    row = []
    for i, city in enumerate(cities):
        row.append(KeyboardButton(text=city))
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    # Добавляем "Любой" и "Назад"
    keyboard.append([KeyboardButton(text="Любой"), KeyboardButton(text="🔙 Назад к регионам")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_main_menu():
    """Главное меню для отправителя"""
    keyboard = [
        [KeyboardButton(text="📦 Отправить груз"), KeyboardButton(text="🚚 Я водитель")],
        [KeyboardButton(text="📋 Мои заявки"), KeyboardButton(text="📞 Поддержка")],
        [KeyboardButton(text="🔄 Перезапустить бота")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_driver_menu():
    """Меню для водителя"""
    keyboard = [
        [KeyboardButton(text="🔍 Искать груз"), KeyboardButton(text="📍 Фильтр по городам")],
        [KeyboardButton(text="⭐ Мой рейтинг"), KeyboardButton(text="📞 Поддержка")],
        [KeyboardButton(text="🔄 Перезапустить бота")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# Клавиатура для запроса контакта (верификация)
contact_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]],
    resize_keyboard=True
)

# ==================== СОСТОЯНИЯ FSM ====================

class CargoStates(StatesGroup):
    # Регистрация
    waiting_for_phone = State()

    # Создание заявки (отправитель)
    waiting_for_sender_region = State()
    waiting_for_from_city = State()
    waiting_for_dest_region = State()
    waiting_for_to_city = State()
    waiting_for_photo = State()
    waiting_for_weight = State()
    waiting_for_volume = State()
    waiting_for_description = State()

    # Фильтрация для водителя
    filter_from_region = State()
    filter_from_city = State()
    filter_to_region = State()
    filter_to_city = State()

    # Для редактирования (сохраняем id старой заявки)
    editing_ad_id = State()  # будет храниться в data

# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if not db.is_user_verified(user_id):
        await message.answer(
            "🔐 Добро пожаловать в сервис попутных грузоперевозок!\n\n"
            "Мы работаем по направлениям:\n"
            "• Хабаровский край\n"
            "• Приморский край\n\n"
            "Для начала работы необходимо подтвердить номер телефона.",
            reply_markup=contact_keyboard
        )
        await state.set_state(CargoStates.waiting_for_phone)
        return
    await message.answer("Главное меню:", reply_markup=get_main_menu())

@dp.message(F.contact, CargoStates.waiting_for_phone)
async def handle_contact(message: types.Message, state: FSMContext):
    if message.contact.user_id != message.from_user.id:
        await message.answer("❌ Отправьте свой номер.", reply_markup=contact_keyboard)
        return
    phone = message.contact.phone_number
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username
    db.save_user(user_id, phone, full_name, username)
    await message.answer("✅ Номер подтверждён!", reply_markup=ReplyKeyboardRemove())
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_menu())

# ==================== ПЕРЕЗАПУСК БОТА ====================

@dp.message(F.text == "🔄 Перезапустить бота")
async def restart_bot(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🔄 **Бот перезапущен!**\n\nВсе предыдущие действия отменены.\nВы можете начать заново.",
        parse_mode="Markdown"
    )
    await message.answer("Главное меню:", reply_markup=get_main_menu())

# ==================== СОЗДАНИЕ ЗАЯВКИ (ОТПРАВИТЕЛЬ) ====================

@dp.message(F.text == "📦 Отправить груз")
async def send_cargo_start(message: types.Message, state: FSMContext):
    await message.answer("Выберите **регион отправления**:", reply_markup=get_regions_keyboard(), parse_mode="Markdown")
    await state.set_state(CargoStates.waiting_for_sender_region)

@dp.message(CargoStates.waiting_for_sender_region)
async def process_sender_region(message: types.Message, state: FSMContext):
    region = message.text
    if region not in REGIONS:
        await message.answer("Пожалуйста, выберите регион из списка.")
        return
    await state.update_data(sender_region=region)
    await message.answer(
        f"Регион отправления: {region}\nТеперь выберите **город отправления**:",
        reply_markup=get_cities_keyboard(region),
        parse_mode="Markdown"
    )
    await state.set_state(CargoStates.waiting_for_from_city)

@dp.message(CargoStates.waiting_for_from_city)
async def process_from_city(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад к регионам":
        await message.answer("Выберите **регион отправления**:", reply_markup=get_regions_keyboard(), parse_mode="Markdown")
        await state.set_state(CargoStates.waiting_for_sender_region)
        return
    data = await state.get_data()
    sender_region = data.get('sender_region')
    cities = REGIONS.get(sender_region, [])
    if message.text not in cities:
        await message.answer("Пожалуйста, выберите город из списка кнопок.")
        return
    await state.update_data(from_city=message.text)
    await message.answer("Выберите **регион назначения**:", reply_markup=get_regions_keyboard(), parse_mode="Markdown")
    await state.set_state(CargoStates.waiting_for_dest_region)

@dp.message(CargoStates.waiting_for_dest_region)
async def process_dest_region(message: types.Message, state: FSMContext):
    region = message.text
    if region not in REGIONS:
        await message.answer("Пожалуйста, выберите регион из списка.")
        return
    await state.update_data(dest_region=region)
    await message.answer(
        f"Регион назначения: {region}\nТеперь выберите **город назначения**:",
        reply_markup=get_cities_keyboard(region),
        parse_mode="Markdown"
    )
    await state.set_state(CargoStates.waiting_for_to_city)

@dp.message(CargoStates.waiting_for_to_city)
async def process_to_city(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад к регионам":
        await message.answer("Выберите **регион назначения**:", reply_markup=get_regions_keyboard(), parse_mode="Markdown")
        await state.set_state(CargoStates.waiting_for_dest_region)
        return
    data = await state.get_data()
    dest_region = data.get('dest_region')
    cities = REGIONS.get(dest_region, [])
    if message.text not in cities:
        await message.answer("Пожалуйста, выберите город из списка кнопок.")
        return
    from_city = data.get('from_city')
    if message.text == from_city:
        await message.answer(
            "Город отправления и назначения не могут совпадать. Выберите другой город.",
            reply_markup=get_cities_keyboard(dest_region)
        )
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
        weight = float(message.text.replace(',', '.'))
        if weight <= 0:
            raise ValueError
        await state.update_data(weight=weight)
        await message.answer("📦 Укажите объём груза (в м³):")
        await state.set_state(CargoStates.waiting_for_volume)
    except ValueError:
        await message.answer("❌ Введите число >0 (например: 50, 100.5)")

@dp.message(CargoStates.waiting_for_volume)
async def process_volume(message: types.Message, state: FSMContext):
    try:
        volume = float(message.text.replace(',', '.'))
        if volume < 0:
            raise ValueError
        await state.update_data(volume=volume)
        await message.answer("📝 Опишите груз подробнее:")
        await state.set_state(CargoStates.waiting_for_description)
    except ValueError:
        await message.answer("❌ Введите число (например: 1, 2.5)")

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

    # Если это редактирование, отменяем старую заявку
    if 'editing_ad_id' in data:
        old_ad_id = data['editing_ad_id']
        db.cancel_ad(old_ad_id, message.from_user.id)
        edit_msg = f"\n\n♻️ Старая заявка #{old_ad_id} отменена."
    else:
        edit_msg = ""

    await message.answer_photo(
        photo=data['photo_file_id'],
        caption=f"✅ **Заявка #{ad_id} создана!**{edit_msg}\n\n"
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
    await message.answer(
        "🚚 **Режим водителя**\n\nТеперь вы можете искать доступные грузы.",
        reply_markup=get_driver_menu(),
        parse_mode="Markdown"
    )

@dp.message(F.text == "🔍 Искать груз")
async def search_cargo(message: types.Message):
    ads = db.get_active_ads()
    if not ads:
        await message.answer("🔍 Пока нет активных заявок.")
        return
    await message.answer(f"🔍 **Найдено заявок: {len(ads)}**\nПоказываю последние:", parse_mode="Markdown")
    for ad in ads[:5]:
        ad_id, user_id, from_city, to_city, weight, volume, description, photo_file_id, created_at = ad
        contact = db.get_user_contact(user_id)  # возвращает @username или имя
        if contact and contact.startswith('@'):
            contact_line = f"👤 **Отправитель:** {contact}\n💬 Нажмите чтобы написать"
        else:
            contact_line = f"👤 **Отправитель:** {contact if contact else 'Неизвестный'}\n📱 (нет username)"
        ad_text = (
            f"📦 **Заявка #{ad_id}**\n"
            f"📍 {from_city} → {to_city}\n"
            f"⚖️ {weight} кг, 📦 {volume} м³\n"
            f"📝 {description}\n"
            f"🕐 {created_at[:16]}\n\n"
            f"{contact_line}"
        )
        try:
            await message.answer_photo(photo=photo_file_id, caption=ad_text, parse_mode="Markdown")
        except:
            await message.answer(ad_text, parse_mode="Markdown")

@dp.message(F.text == "📍 Фильтр по городам")
async def filter_start(message: types.Message, state: FSMContext):
    await message.answer("Выберите **регион отправления** для фильтрации:", reply_markup=get_regions_keyboard(), parse_mode="Markdown")
    await state.set_state(CargoStates.filter_from_region)

@dp.message(CargoStates.filter_from_region)
async def filter_from_region(message: types.Message, state: FSMContext):
    region = message.text
    if region not in REGIONS:
        await message.answer("Пожалуйста, выберите регион из списка.")
        return
    await state.update_data(filter_from_region=region)
    await message.answer(
        f"Регион отправления: {region}\nТеперь выберите **город отправления** (или 'Любой'):",
        reply_markup=get_cities_keyboard_with_any(region),
        parse_mode="Markdown"
    )
    await state.set_state(CargoStates.filter_from_city)

@dp.message(CargoStates.filter_from_city)
async def filter_from_city(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад к регионам":
        await message.answer("Выберите **регион отправления**:", reply_markup=get_regions_keyboard(), parse_mode="Markdown")
        await state.set_state(CargoStates.filter_from_region)
        return
    from_city = None if message.text == "Любой" else message.text
    await state.update_data(filter_from_city=from_city)
    await message.answer("Выберите **регион назначения** для фильтрации:", reply_markup=get_regions_keyboard(), parse_mode="Markdown")
    await state.set_state(CargoStates.filter_to_region)

@dp.message(CargoStates.filter_to_region)
async def filter_to_region(message: types.Message, state: FSMContext):
    region = message.text
    if region not in REGIONS:
        await message.answer("Пожалуйста, выберите регион из списка.")
        return
    await state.update_data(filter_to_region=region)
    await message.answer(
        f"Регион назначения: {region}\nТеперь выберите **город назначения** (или 'Любой'):",
        reply_markup=get_cities_keyboard_with_any(region),
        parse_mode="Markdown"
    )
    await state.set_state(CargoStates.filter_to_city)

@dp.message(CargoStates.filter_to_city)
async def filter_to_city(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад к регионам":
        await message.answer("Выберите **регион назначения**:", reply_markup=get_regions_keyboard(), parse_mode="Markdown")
        await state.set_state(CargoStates.filter_to_region)
        return
    to_city = None if message.text == "Любой" else message.text
    data = await state.get_data()
    from_city = data.get('filter_from_city')
    ads = db.get_active_ads(from_city, to_city)
    if not ads:
        await message.answer("🔍 По заданному направлению заявок не найдено.")
    else:
        await message.answer(f"🔍 **Найдено заявок: {len(ads)}**", parse_mode="Markdown")
        for ad in ads[:5]:
            ad_id, user_id, f_city, t_city, weight, volume, description, photo_file_id, created_at = ad
            contact = db.get_user_contact(user_id)
            if contact and contact.startswith('@'):
                contact_line = f"👤 **Отправитель:** {contact}\n💬 Нажмите чтобы написать"
            else:
                contact_line = f"👤 **Отправитель:** {contact if contact else 'Неизвестный'}\n📱 (нет username)"
            ad_text = (
                f"📦 **Заявка #{ad_id}**\n"
                f"📍 {f_city} → {t_city}\n"
                f"⚖️ {weight} кг, 📦 {volume} м³\n"
                f"📝 {description}\n"
                f"🕐 {created_at[:16]}\n\n"
                f"{contact_line}"
            )
            try:
                await message.answer_photo(photo=photo_file_id, caption=ad_text, parse_mode="Markdown")
            except:
                await message.answer(ad_text, parse_mode="Markdown")
    await state.clear()

# ==================== МОИ ЗАЯВКИ (ОТПРАВИТЕЛЬ) ====================

@dp.message(F.text == "📋 Мои заявки")
async def my_ads(message: types.Message):
    user_id = message.from_user.id
    ads = db.get_user_ads(user_id)
    if not ads:
        await message.answer("📭 У вас пока нет активных заявок.")
        return
    await message.answer(f"📋 **Ваши активные заявки:** ({len(ads)})", parse_mode="Markdown")
    for ad in ads:
        ad_id, from_city, to_city, weight, volume, description, photo_file_id, created_at = ad
        ad_text = (
            f"📦 **Заявка #{ad_id}**\n"
            f"📍 {from_city} → {to_city}\n"
            f"⚖️ {weight} кг, 📦 {volume} м³\n"
            f"📝 {description}\n"
            f"🕐 {created_at[:16]}"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить", callback_data=f"edit_{ad_id}"),
             InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{ad_id}")]
        ])
        try:
            await message.answer_photo(photo=photo_file_id, caption=ad_text, reply_markup=keyboard, parse_mode="Markdown")
        except:
            await message.answer(ad_text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_ad_callback(callback: types.CallbackQuery):
    ad_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    if db.cancel_ad(ad_id, user_id):
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n❌ **Заявка отменена**",
            parse_mode="Markdown"
        )
        await callback.answer("✅ Заявка отменена")
    else:
        await callback.answer("❌ Не удалось отменить", show_alert=True)

@dp.callback_query(F.data.startswith("edit_"))
async def edit_ad_callback(callback: types.CallbackQuery, state: FSMContext):
    ad_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    conn = sqlite3.connect('cargo_bot.db')
    c = conn.cursor()
    c.execute('''SELECT from_city, to_city, weight, volume, description, photo_file_id 
                 FROM cargo_ads WHERE id = ? AND user_id = ?''', (ad_id, user_id))
    ad = c.fetchone()
    conn.close()
    if not ad:
        await callback.answer("❌ Заявка не найдена", show_alert=True)
        return
    from_city, to_city, weight, volume, description, photo_file_id = ad
    # Определим регионы по городам (упрощённо: ищем в REGIONS)
    sender_region = None
    dest_region = None
    for region, cities in REGIONS.items():
        if from_city in cities:
            sender_region = region
        if to_city in cities:
            dest_region = region
    await state.update_data(
        from_city=from_city,
        to_city=to_city,
        weight=weight,
        volume=volume,
        description=description,
        photo_file_id=photo_file_id,
        sender_region=sender_region,
        dest_region=dest_region,
        editing_ad_id=ad_id
    )
    await callback.message.answer(
        "🔄 **Редактирование заявки**\n\n"
        "Текущие данные загружены. Хотите загрузить новое фото? (отправьте фото или пропустите)",
        parse_mode="Markdown"
    )
    await state.set_state(CargoStates.waiting_for_photo)
    await callback.answer()

# ==================== РЕЙТИНГ И ОТЗЫВЫ ====================
# (Базовая реализация: возможность оставить отзыв после завершения заявки)

# Функция для завершения заявки (может вызываться водителем или отправителем)
# В реальности нужно добавить кнопку "Заявка выполнена" в моих заявках или в поиске.
# Упростим: добавим команду /complete для демонстрации

@dp.message(Command("complete"))
async def complete_ad(message: types.Message):
    # Эта команда будет завершать заявку и предлагать оставить отзыв
    # В реальном проекте нужно добавить логику выбора заявки, здесь просто пример
    await message.answer("Эта функция в разработке. Скоро вы сможете оставлять отзывы.")

@dp.message(F.text == "⭐ Мой рейтинг")
async def show_rating(message: types.Message):
    user_id = message.from_user.id
    rating = db.get_user_rating(user_id)  # функция из database.py
    await message.answer(
        f"⭐ **Ваш рейтинг:** {rating}\n\n"
        "Рейтинг формируется на основе отзывов после завершённых поездок.",
        parse_mode="Markdown"
    )

# ==================== ПОДДЕРЖКА ====================

@dp.message(F.text == "📞 Поддержка")
async def support(message: types.Message):
    await message.answer(
        "📞 **Поддержка**\n\nПо всем вопросам пишите: @Miaov3\nВремя ответа: обычно в течение часа.",
        parse_mode="Markdown"
    )

# ==================== ОБРАБОТКА НЕИЗВЕСТНЫХ КОМАНД ====================

@dp.message()
async def handle_unknown(message: types.Message):
    await message.answer(
        "Я не понял команду. Используйте кнопки меню или напишите /start",
        reply_markup=get_main_menu()
    )

# ==================== ВЕБ-СЕРВЕР ДЛЯ RENDER ====================

async def handle_http(request):
    return web.Response(text="Бот работает! 🤖")

async def run_web_server():
    app = web.Application()
    app.router.add_get('/', handle_http)
    app.router.add_get('/health', handle_http)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    print("🌐 Веб-сервер запущен на порту 10000")

async def main():
    await asyncio.gather(
        dp.start_polling(bot),
        run_web_server()
    )

# ==================== ТОЧКА ВХОДА ====================

if __name__ == "__main__":
    db.init_db()
    print("🚀 Бот запущен...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Бот остановлен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
