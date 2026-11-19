"""
PostgreSQL база данных для NFT парсера с подписками
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from contextlib import contextmanager
from datetime import datetime, timedelta
import logging
import random
import string

log = logging.getLogger('parser.db')


class DatabasePG:
    """PostgreSQL database wrapper для парсера"""
    
    def __init__(self, database_url: str):
        """
        Инициализация подключения к PostgreSQL
        
        Args:
            database_url: postgres://user:password@host:port/database
        """
        self.database_url = database_url
        self.pool = SimpleConnectionPool(1, 10, database_url)
        log.info('PostgreSQL pool создан')
    
    @contextmanager
    def _get_conn(self):
        """Контекстный менеджер для получения подключения из пула"""
        conn = self.pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)
    
    def init_tables(self):
        """Создание всех необходимых таблиц"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                # Таблица пользователей бота
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        subscription_until TIMESTAMP,
                        total_parsings INTEGER DEFAULT 0,
                        total_found_nft INTEGER DEFAULT 0,
                        last_parsing_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Таблица платежей
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS payments (
                        payment_id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(user_id),
                        amount DECIMAL(10,2),
                        memo TEXT UNIQUE NOT NULL,
                        status TEXT DEFAULT 'pending',
                        tx_hash TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP
                    )
                ''')
                
                # Таблица сессий парсинга
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS parser_sessions (
                        session_id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(user_id),
                        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        found_count INTEGER DEFAULT 0,
                        status TEXT DEFAULT 'running'
                    )
                ''')
                
                # Таблица найденных владельцев NFT
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS found_nft_users (
                        id SERIAL PRIMARY KEY,
                        session_id INTEGER REFERENCES parser_sessions(session_id),
                        nft_owner_user_id BIGINT NOT NULL,
                        nft_owner_username TEXT,
                        nft_owner_first_name TEXT,
                        chat_id BIGINT,
                        chat_title TEXT,
                        nft_count INTEGER,
                        found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(session_id, nft_owner_user_id)
                    )
                ''')
                
                # Таблица NFT подарков
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS nft_gifts (
                        id SERIAL PRIMARY KEY,
                        found_user_id INTEGER REFERENCES found_nft_users(id),
                        gift_id TEXT,
                        gift_name TEXT,
                        gift_slug TEXT,
                        gift_num INTEGER,
                        can_upgrade BOOLEAN DEFAULT FALSE,
                        is_collectible BOOLEAN DEFAULT FALSE
                    )
                ''')
                
                # Таблица чатов для парсинга
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS parser_chats (
                        chat_id BIGINT PRIMARY KEY,
                        title TEXT,
                        username TEXT,
                        is_active BOOLEAN DEFAULT TRUE,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Таблица для хранения сессии Telethon
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS parser_session (
                        id SERIAL PRIMARY KEY,
                        owner_id BIGINT NOT NULL,
                        session_string TEXT NOT NULL,
                        phone TEXT,
                        username TEXT,
                        user_id BIGINT,
                        first_name TEXT,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Глобальная дедупликация просмотренных пользователей
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS global_seen_users (
                        user_id BIGINT PRIMARY KEY,
                        first_seen_by BIGINT,
                        first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                log.info('Все таблицы созданы/проверены')
    
    # ============== USERS ==============
    
    def get_or_create_user(self, user_id: int, username: str = None, first_name: str = None):
        """Получить или создать пользователя"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('''
                    INSERT INTO users (user_id, username, first_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name
                    RETURNING *
                ''', (user_id, username, first_name))
                return dict(cur.fetchone())
    
    def has_active_subscription(self, user_id: int) -> bool:
        """Проверить есть ли активная подписка"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT subscription_until FROM users 
                    WHERE user_id = %s AND subscription_until > CURRENT_TIMESTAMP
                ''', (user_id,))
                return cur.fetchone() is not None
    
    def get_subscription_until(self, user_id: int):
        """Получить время окончания подписки"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT subscription_until FROM users WHERE user_id = %s', (user_id,))
                row = cur.fetchone()
                return row[0] if row else None
    
    def add_subscription(self, user_id: int, hours: int = 24):
        """Добавить подписку пользователю"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    UPDATE users SET subscription_until = 
                    CASE 
                        WHEN subscription_until IS NULL OR subscription_until < CURRENT_TIMESTAMP 
                        THEN CURRENT_TIMESTAMP + INTERVAL '%s hours'
                        ELSE subscription_until + INTERVAL '%s hours'
                    END
                    WHERE user_id = %s
                ''', (hours, hours, user_id))
    
    def get_user(self, user_id: int):
        """Получить данные пользователя"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
                row = cur.fetchone()
                return dict(row) if row else None
    
    def get_all_users(self):
        """Получить всех пользователей"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT * FROM users ORDER BY created_at DESC')
                return [dict(row) for row in cur.fetchall()]
    
    def get_active_subscribers(self):
        """Получить пользователей с активной подпиской"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('''
                    SELECT * FROM users 
                    WHERE subscription_until > CURRENT_TIMESTAMP 
                    ORDER BY subscription_until DESC
                ''')
                return [dict(row) for row in cur.fetchall()]
    
    # ============== PAYMENTS ==============
    
    def create_payment(self, user_id: int, amount: float) -> str:
        """Создать платёж и вернуть уникальный MEMO"""
        memo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO payments (user_id, amount, memo, status)
                    VALUES (%s, %s, %s, 'pending')
                ''', (user_id, amount, memo))
        return memo
    
    def get_payment_by_memo(self, memo: str):
        """Получить платёж по MEMO"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT * FROM payments WHERE memo = %s', (memo,))
                row = cur.fetchone()
                return dict(row) if row else None
    
    def complete_payment(self, memo: str, tx_hash: str = None):
        """Отметить платёж как выполненный"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    UPDATE payments 
                    SET status = 'completed', tx_hash = %s, completed_at = CURRENT_TIMESTAMP
                    WHERE memo = %s
                ''', (tx_hash, memo))
    
    def get_all_payments(self):
        """Получить все платежи"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT * FROM payments ORDER BY created_at DESC')
                return [dict(row) for row in cur.fetchall()]
    
    def get_pending_payments(self):
        """Получить ожидающие платежи"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('''
                    SELECT * FROM payments 
                    WHERE status = 'pending' 
                    ORDER BY created_at DESC
                ''')
                return [dict(row) for row in cur.fetchall()]
    
    # ============== PARSER SESSIONS ==============
    
    def create_parser_session(self, user_id: int) -> int:
        """Создать новую сессию парсинга"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO parser_sessions (user_id, status)
                    VALUES (%s, 'running')
                    RETURNING session_id
                ''', (user_id,))
                return cur.fetchone()[0]
    
    def complete_parser_session(self, session_id: int, found_count: int):
        """Завершить сессию парсинга"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    UPDATE parser_sessions 
                    SET status = 'completed', completed_at = CURRENT_TIMESTAMP, found_count = %s
                    WHERE session_id = %s
                ''', (found_count, session_id))
                
                # Обновить статистику пользователя
                cur.execute('''
                    UPDATE users 
                    SET total_parsings = total_parsings + 1,
                        total_found_nft = total_found_nft + %s,
                        last_parsing_at = CURRENT_TIMESTAMP
                    WHERE user_id = (SELECT user_id FROM parser_sessions WHERE session_id = %s)
                ''', (found_count, session_id))
    
    def get_last_parsing_time(self, user_id: int):
        """Получить время последнего парсинга пользователя"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT MAX(started_at) FROM parser_sessions 
                    WHERE user_id = %s AND status = 'completed'
                ''', (user_id,))
                row = cur.fetchone()
                return row[0] if row and row[0] else None
    
    def can_start_parsing(self, user_id: int, cooldown_minutes: int = 5) -> bool:
        """Проверить может ли пользователь начать парсинг (кулдаун)"""
        last_time = self.get_last_parsing_time(user_id)
        if not last_time:
            return True
        
        time_passed = datetime.now() - last_time
        return time_passed.total_seconds() >= (cooldown_minutes * 60)
    
    # ============== FOUND NFT USERS ==============
    
    def add_found_nft_user(self, session_id: int, nft_owner_user_id: int, 
                          nft_owner_username: str = None, nft_owner_first_name: str = None,
                          chat_id: int = None, chat_title: str = None, nft_count: int = 1) -> int:
        """Добавить найденного владельца NFT"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO found_nft_users 
                    (session_id, nft_owner_user_id, nft_owner_username, nft_owner_first_name, chat_id, chat_title, nft_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (session_id, nft_owner_user_id) DO NOTHING
                    RETURNING id
                ''', (session_id, nft_owner_user_id, nft_owner_username, nft_owner_first_name, chat_id, chat_title, nft_count))
                result = cur.fetchone()
                return result[0] if result else None
    
    def add_nft_gift(self, found_user_id: int, gift_id: str, gift_name: str = None,
                    gift_slug: str = None, gift_num: int = None, 
                    can_upgrade: bool = False, is_collectible: bool = False):
        """Добавить NFT подарок"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO nft_gifts 
                    (found_user_id, gift_id, gift_name, gift_slug, gift_num, can_upgrade, is_collectible)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (found_user_id, str(gift_id), gift_name, gift_slug, gift_num, can_upgrade, is_collectible))
    
    def get_session_found_users(self, session_id: int):
        """Получить найденных пользователей в сессии"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('''
                    SELECT * FROM found_nft_users 
                    WHERE session_id = %s 
                    ORDER BY found_at
                ''', (session_id,))
                return [dict(row) for row in cur.fetchall()]
    
    def get_user_nft_gifts(self, found_user_id: int):
        """Получить NFT подарки найденного пользователя"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('''
                    SELECT * FROM nft_gifts 
                    WHERE found_user_id = %s
                ''', (found_user_id,))
                return [dict(row) for row in cur.fetchall()]
    
    # ============== GLOBAL SEEN USERS ==============
    
    def is_user_globally_seen(self, user_id: int) -> bool:
        """Проверить был ли пользователь уже найден кем-то"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT 1 FROM global_seen_users WHERE user_id = %s', (user_id,))
                return cur.fetchone() is not None
    
    def mark_user_globally_seen(self, user_id: int, found_by_user_id: int):
        """Отметить пользователя как найденного"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO global_seen_users (user_id, first_seen_by)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                ''', (user_id, found_by_user_id))
    
    # ============== PARSER CHATS ==============
    
    def add_parser_chat(self, chat_id: int, title: str, username: str = None):
        """Добавить чат для парсинга"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO parser_chats (chat_id, title, username)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (chat_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        username = EXCLUDED.username
                ''', (chat_id, title, username))
    
    def get_active_parser_chats(self):
        """Получить активные чаты для парсинга (рандомный порядок)"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('''
                    SELECT * FROM parser_chats 
                    WHERE is_active = TRUE 
                    ORDER BY RANDOM()
                ''')
                return [dict(row) for row in cur.fetchall()]
    
    def get_all_parser_chats(self):
        """Получить все чаты"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT * FROM parser_chats ORDER BY title')
                return [dict(row) for row in cur.fetchall()]
    
    def toggle_parser_chat(self, chat_id: int):
        """Переключить активность чата"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    UPDATE parser_chats 
                    SET is_active = NOT is_active 
                    WHERE chat_id = %s
                ''', (chat_id,))
    
    def delete_parser_chat(self, chat_id: int):
        """Удалить чат"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM parser_chats WHERE chat_id = %s', (chat_id,))
    
    # ============== PARSER SESSION (Telethon) ==============
    
    def save_parser_session(self, owner_id: int, session_string: str, phone: str = None,
                           username: str = None, user_id: int = None, first_name: str = None):
        """Сохранить сессию парсер-аккаунта"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM parser_session')
                cur.execute('''
                    INSERT INTO parser_session 
                    (owner_id, session_string, phone, username, user_id, first_name, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                ''', (owner_id, session_string, phone, username, user_id, first_name))
                log.info('Сессия сохранена для user_id=%s', user_id)
    
    def get_parser_session(self):
        """Получить текущую сессию парсера"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT * FROM parser_session ORDER BY id DESC LIMIT 1')
                row = cur.fetchone()
                return dict(row) if row else None
    
    # ============== ADMIN STATS ==============
    
    def get_admin_stats(self):
        """Получить статистику для админки"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('''
                    SELECT 
                        (SELECT COUNT(*) FROM users) as total_users,
                        (SELECT COUNT(*) FROM users WHERE subscription_until > CURRENT_TIMESTAMP) as active_subscriptions,
                        (SELECT COUNT(*) FROM parser_sessions WHERE status = 'completed') as total_parsings,
                        (SELECT SUM(found_count) FROM parser_sessions WHERE status = 'completed') as total_found_nft,
                        (SELECT SUM(amount) FROM payments WHERE status = 'completed') as total_revenue,
                        (SELECT COUNT(*) FROM parser_chats WHERE is_active = TRUE) as active_chats
                ''')
                row = cur.fetchone()
                return dict(row) if row else {}
