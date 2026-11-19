"""
PostgreSQL база данных для парсера NFT подарков
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from contextlib import contextmanager
import logging

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
        log.info('✅ PostgreSQL pool создан')
    
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
                # Таблица для хранения сессии парсер-аккаунта
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
                
                # Таблица для списка чатов
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS parser_chats (
                        id SERIAL PRIMARY KEY,
                        chat_id BIGINT UNIQUE NOT NULL,
                        title TEXT,
                        username TEXT,
                        chat_type TEXT,
                        participants_count INTEGER DEFAULT 0,
                        is_enabled BOOLEAN DEFAULT TRUE,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Таблица для найденных пользователей с NFT
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS parser_users (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        username TEXT,
                        first_name TEXT,
                        source_chat_id BIGINT,
                        source_chat_title TEXT,
                        has_gifts BOOLEAN DEFAULT FALSE,
                        gifts_count INTEGER DEFAULT 0,
                        checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, source_chat_id)
                    )
                ''')
                
                # Таблица для найденных подарков
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS parser_gifts (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        gift_id TEXT,
                        gift_name TEXT,
                        gift_slug TEXT,
                        gift_num INTEGER,
                        can_upgrade BOOLEAN DEFAULT FALSE,
                        is_collectible BOOLEAN DEFAULT FALSE,
                        estimated_price INTEGER DEFAULT 0,
                        found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, gift_id, gift_num)
                    )
                ''')
                
                # Таблица состояния сканирования
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS parser_scan_state (
                        id SERIAL PRIMARY KEY,
                        owner_id BIGINT NOT NULL,
                        mode TEXT,
                        max_users INTEGER,
                        status TEXT DEFAULT 'idle',
                        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP
                    )
                ''')
                
                log.info('✅ Все таблицы созданы/проверены')
    
    # ============== PARSER SESSION ==============
    
    def save_parser_session(self, owner_id: int, session_string: str, phone: str = None,
                           username: str = None, user_id: int = None, first_name: str = None):
        """Сохранить сессию парсер-аккаунта"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                # Удаляем старую сессию
                cur.execute('DELETE FROM parser_session')
                
                # Вставляем новую
                cur.execute('''
                    INSERT INTO parser_session 
                    (owner_id, session_string, phone, username, user_id, first_name, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                ''', (owner_id, session_string, phone, username, user_id, first_name))
                
                log.info('✅ Сессия сохранена для user_id=%s', user_id)
    
    def get_parser_session(self):
        """Получить текущую сессию парсера"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT * FROM parser_session ORDER BY id DESC LIMIT 1')
                row = cur.fetchone()
                return dict(row) if row else None
    
    def set_parser_active(self, is_active: bool):
        """Установить статус активности парсера"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE parser_session SET is_active = %s', (is_active,))
    
    def clear_parser_session(self):
        """Удалить сессию парсера"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM parser_session')
                log.info('🗑 Сессия парсера удалена')
    
    # ============== PARSER CHATS ==============
    
    def add_parser_chat(self, chat_id: int, title: str, username: str = None,
                       chat_type: str = None, participants_count: int = 0):
        """Добавить чат в список"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO parser_chats (chat_id, title, username, chat_type, participants_count)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (chat_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        username = EXCLUDED.username,
                        participants_count = EXCLUDED.participants_count
                ''', (chat_id, title, username, chat_type, participants_count))
    
    def get_parser_chats(self):
        """Получить список всех чатов"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT * FROM parser_chats ORDER BY title')
                return [dict(row) for row in cur.fetchall()]
    
    def get_enabled_parser_chats(self):
        """Получить список активных чатов"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT * FROM parser_chats WHERE is_enabled = TRUE ORDER BY title')
                return [dict(row) for row in cur.fetchall()]
    
    def toggle_parser_chat(self, chat_id: int):
        """Переключить статус чата (вкл/выкл)"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    UPDATE parser_chats 
                    SET is_enabled = NOT is_enabled 
                    WHERE chat_id = %s
                ''', (chat_id,))
    
    def set_all_parser_chats(self, enabled: bool):
        """Включить/выключить все чаты"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE parser_chats SET is_enabled = %s', (enabled,))
    
    # ============== PARSER USERS & GIFTS ==============
    
    def add_parser_user(self, user_id: int, username: str = None, first_name: str = None,
                       source_chat_id: int = None, source_chat_title: str = None,
                       has_gifts: bool = False, gifts_count: int = 0):
        """Добавить найденного пользователя"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO parser_users 
                    (user_id, username, first_name, source_chat_id, source_chat_title, has_gifts, gifts_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, source_chat_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        has_gifts = EXCLUDED.has_gifts,
                        gifts_count = EXCLUDED.gifts_count,
                        checked_at = CURRENT_TIMESTAMP
                ''', (user_id, username, first_name, source_chat_id, source_chat_title, has_gifts, gifts_count))
    
    def add_parser_gift(self, user_id: int, gift_id: str, gift_name: str = None,
                       gift_slug: str = None, gift_num: int = None, can_upgrade: bool = False,
                       is_collectible: bool = False, estimated_price: int = 0):
        """Добавить найденный подарок"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO parser_gifts 
                    (user_id, gift_id, gift_name, gift_slug, gift_num, can_upgrade, is_collectible, estimated_price)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, gift_id, gift_num) DO NOTHING
                ''', (user_id, gift_id, gift_name, gift_slug, gift_num, can_upgrade, is_collectible, estimated_price))
    
    def get_parser_stats(self):
        """Получить статистику парсера"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('''
                    SELECT 
                        (SELECT COUNT(*) FROM parser_chats) as total_chats,
                        (SELECT COUNT(*) FROM parser_chats WHERE is_enabled = TRUE) as enabled_chats,
                        (SELECT COUNT(*) FROM parser_users) as total_users,
                        (SELECT COUNT(*) FROM parser_users WHERE has_gifts = TRUE) as users_with_gifts,
                        (SELECT COUNT(*) FROM parser_gifts) as total_gifts,
                        (SELECT COUNT(*) FROM parser_gifts WHERE can_upgrade = TRUE) as unupgraded_gifts
                ''')
                row = cur.fetchone()
                return dict(row) if row else {}
    
    # ============== PARSER SCAN STATE ==============
    
    def save_parser_scan_state(self, owner_id: int, mode: str, max_users: int, status: str = 'running'):
        """Сохранить состояние сканирования"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                # Удаляем старые записи
                cur.execute('DELETE FROM parser_scan_state WHERE owner_id = %s', (owner_id,))
                
                # Вставляем новую
                cur.execute('''
                    INSERT INTO parser_scan_state (owner_id, mode, max_users, status)
                    VALUES (%s, %s, %s, %s)
                ''', (owner_id, mode, max_users, status))
    
    def get_parser_scan_state(self):
        """Получить текущее состояние сканирования"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT * FROM parser_scan_state ORDER BY id DESC LIMIT 1')
                row = cur.fetchone()
                return dict(row) if row else None
    
    def update_parser_scan_status(self, status: str):
        """Обновить статус сканирования"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    UPDATE parser_scan_state 
                    SET status = %s, completed_at = CURRENT_TIMESTAMP
                    WHERE id = (SELECT id FROM parser_scan_state ORDER BY id DESC LIMIT 1)
                ''', (status,))
