import sqlite3
import datetime

DB_PATH = 'cargo_bot.db'

def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  phone TEXT UNIQUE,
                  full_name TEXT,
                  is_verified BOOLEAN DEFAULT 0,
                  joined_at TIMESTAMP)''')
    
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
                  status TEXT DEFAULT 'active')''')
    
    conn.commit()
    conn.close()

def save_user(user_id, phone, full_name):
    """Сохранение пользователя"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO users 
                 (user_id, phone, full_name, is_verified, joined_at)
                 VALUES (?, ?, ?, 1, ?)''',
              (user_id, phone, full_name, datetime.datetime.now()))
    conn.commit()
    conn.close()

def is_user_verified(user_id):
    """Проверка верификации пользователя"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT is_verified FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else False

def save_cargo_ad(user_id, from_city, to_city, weight, volume, description, photo_file_id):
    """Сохранение заявки на груз"""
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
    """Получение активных заявок с фильтрацией"""
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
def get_user_username(user_id):
    """Получить username пользователя по его ID"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT full_name FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        conn.close()
        
        if result and result[0]:
            # Проверяем, похоже ли имя на username (начинается с @)
            name = result[0]
            if not name.startswith('@'):
                # Если не начинается с @, добавляем @ к имени
                # Но лучше, чтобы пользователи сами указывали username
                return f"@{name}"
            return name
        else:
            return f"Пользователь {user_id}"
    except Exception as e:
        print(f"Ошибка получения username: {e}")
        return f"Пользователь {user_id}"
def get_user_phone(user_id):
    """Получить номер телефона пользователя по его ID"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT phone FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if result:
        return result[0]
    return "Телефон не указан"
