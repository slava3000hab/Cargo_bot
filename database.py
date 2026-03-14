import sqlite3
import datetime

DB_PATH = 'cargo_bot.db'

# ==================== ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ====================

def init_db():
    """Создаёт все необходимые таблицы, если их нет"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  phone TEXT UNIQUE,
                  full_name TEXT,
                  username TEXT,
                  is_verified BOOLEAN DEFAULT 0,
                  joined_at TIMESTAMP,
                  rating REAL DEFAULT 0,
                  reviews_count INTEGER DEFAULT 0)''')

    # Таблица заявок на груз
    c.execute('''CREATE TABLE IF NOT EXISTS cargo_ads
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  from_city TEXT,
                  to_city TEXT,
                  weight REAL,
                  volume REAL,
                  description TEXT,
                  photo_file_id TEXT,
                  created_at TIMESTAMP,
                  status TEXT DEFAULT 'active',
                  FOREIGN KEY(user_id) REFERENCES users(user_id))''')

    # Таблица отзывов
    c.execute('''CREATE TABLE IF NOT EXISTS reviews
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  from_user INTEGER,
                  to_user INTEGER,
                  ad_id INTEGER,
                  rating INTEGER CHECK(rating BETWEEN 1 AND 5),
                  comment TEXT,
                  created_at TIMESTAMP,
                  FOREIGN KEY(from_user) REFERENCES users(user_id),
                  FOREIGN KEY(to_user) REFERENCES users(user_id),
                  FOREIGN KEY(ad_id) REFERENCES cargo_ads(id))''')

    conn.commit()
    conn.close()

# ==================== РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ====================

def save_user(user_id, phone, full_name, username=None):
    """Сохраняет или обновляет пользователя"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Убеждаемся, что поле username существует (для старых баз)
    c.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in c.fetchall()]
    if 'username' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN username TEXT")
    if 'rating' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN rating REAL DEFAULT 0")
    if 'reviews_count' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN reviews_count INTEGER DEFAULT 0")

    c.execute('''INSERT OR REPLACE INTO users 
                 (user_id, phone, full_name, username, is_verified, joined_at, rating, reviews_count)
                 VALUES (?, ?, ?, ?, 1, ?, COALESCE((SELECT rating FROM users WHERE user_id=?), 0),
                         COALESCE((SELECT reviews_count FROM users WHERE user_id=?), 0))''',
              (user_id, phone, full_name, username, datetime.datetime.now(), user_id, user_id))
    conn.commit()
    conn.close()

def is_user_verified(user_id):
    """Проверяет, подтверждён ли пользователь"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT is_verified FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else False

def get_user_username(user_id):
    """Возвращает username пользователя (с @) или None"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT username FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        conn.close()
        if result and result[0]:
            return f"@{result[0]}"
        return None
    except Exception as e:
        print(f"Ошибка получения username: {e}")
        return None

def get_user_contact(user_id):
    """
    Возвращает строку для отображения контакта отправителя.
    Приоритет: username (с @) > full_name > None
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT username, full_name FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        if row:
            username, full_name = row
            if username:
                return f"@{username}"
            elif full_name:
                return full_name
        return None
    except Exception as e:
        print(f"Ошибка get_user_contact: {e}")
        return None

def update_user_username(user_id, username):
    """Обновляет username пользователя (используется при редактировании)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in c.fetchall()]
        if 'username' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN username TEXT")
        c.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка обновления username: {e}")
        return False

# ==================== РАБОТА С ЗАЯВКАМИ ====================

def save_cargo_ad(user_id, from_city, to_city, weight, volume, description, photo_file_id):
    """Сохраняет новую заявку"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO cargo_ads 
                 (user_id, from_city, to_city, weight, volume, description, photo_file_id, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (user_id, from_city, to_city, weight, volume, description, photo_file_id, datetime.datetime.now()))
    ad_id = c.lastrowid
    conn.commit()
    conn.close()
    return ad_id

def get_active_ads(from_city=None, to_city=None):
    """
    Возвращает активные заявки с возможностью фильтрации по городам.
    Если from_city или to_city равны None, фильтр не применяется.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    query = '''SELECT id, user_id, from_city, to_city, weight, volume, description, photo_file_id, created_at 
               FROM cargo_ads 
               WHERE status = 'active' '''
    params = []
    if from_city:
        query += " AND from_city = ?"
        params.append(from_city)
    if to_city:
        query += " AND to_city = ?"
        params.append(to_city)
    query += " ORDER BY created_at DESC LIMIT 20"
    c.execute(query, params)
    ads = c.fetchall()
    conn.close()
    return ads

def get_user_ads(user_id):
    """Возвращает все активные заявки конкретного пользователя"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT id, from_city, to_city, weight, volume, description, photo_file_id, created_at 
                 FROM cargo_ads 
                 WHERE user_id = ? AND status = 'active'
                 ORDER BY created_at DESC''', (user_id,))
    ads = c.fetchall()
    conn.close()
    return ads

def cancel_ad(ad_id, user_id):
    """Отменяет заявку (меняет статус на 'cancelled')"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE cargo_ads SET status = 'cancelled' WHERE id = ? AND user_id = ?", (ad_id, user_id))
    success = c.rowcount > 0
    conn.commit()
    conn.close()
    return success

# ==================== РАБОТА С ОТЗЫВАМИ И РЕЙТИНГОМ ====================

def save_review(from_user, to_user, ad_id, rating, comment):
    """Сохраняет отзыв и обновляет рейтинг пользователя"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Вставляем отзыв
    c.execute('''INSERT INTO reviews (from_user, to_user, ad_id, rating, comment, created_at)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (from_user, to_user, ad_id, rating, comment, datetime.datetime.now()))
    # Обновляем средний рейтинг пользователя
    c.execute('''UPDATE users 
                 SET rating = (SELECT AVG(rating) FROM reviews WHERE to_user = ?),
                     reviews_count = (SELECT COUNT(*) FROM reviews WHERE to_user = ?)
                 WHERE user_id = ?''', (to_user, to_user, to_user))
    conn.commit()
    conn.close()

def get_user_rating(user_id):
    """Возвращает средний рейтинг пользователя (0, если отзывов нет)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT rating FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0.0

def get_user_reviews(user_id):
    """Возвращает список отзывов о пользователе"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT from_user, rating, comment, created_at 
                 FROM reviews WHERE to_user = ? ORDER BY created_at DESC''', (user_id,))
    reviews = c.fetchall()
    conn.close()
    return reviews
