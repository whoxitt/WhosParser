"""
Telethon клиент для парсера с поддержкой авторизации через номер телефона
"""
import logging
import os
import asyncio
from typing import Any

from dotenv import load_dotenv
from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    FloodWaitError,
)

load_dotenv()
log = logging.getLogger('parser.client')

# Telegram API credentials
API_ID = int(os.getenv('TG_API_ID', '2040'))
API_HASH = os.getenv('TG_API_HASH', 'b18441a1ff607e10a989891a5462e627')


class ParserClient:
    """Telethon клиент для работы с парсером"""
    
    def __init__(self, session_string: str = ''):
        """
        Args:
            session_string: StringSession для восстановления сессии (опционально)
        """
        self.session_string = session_string.strip()
        self.client: TelegramClient | None = None
        self._phone: str | None = None
        self._phone_code_hash: str | None = None
    
    async def _ensure_client(self):
        """Создать клиент если его нет"""
        if self.client is None:
            self.client = TelegramClient(
                StringSession(self.session_string),
                API_ID,
                API_HASH
            )
        if not self.client.is_connected():
            await self.client.connect()
    
    async def send_code(self, phone: str):
        """
        Отправить код подтверждения на номер телефона
        
        Args:
            phone: Номер телефона в формате +79991234567
        """
        self._phone = phone
        await self._ensure_client()
        
        # Проверяем авторизацию
        if await self.client.is_user_authorized():
            log.info('Пользователь уже авторизован')
            return False
        
        # Отправляем код
        result = await self.client.send_code_request(phone)
        self._phone_code_hash = result.phone_code_hash
        log.info('✅ Код отправлен на номер %s', phone)
        return True
    
    async def sign_in(self, phone: str, code: str):
        """
        Войти с помощью кода подтверждения
        
        Args:
            phone: Номер телефона
            code: Код подтверждения (без пробелов)
        """
        if not self.client or not self._phone_code_hash:
            raise RuntimeError('Сначала вызовите send_code()')
        
        try:
            await self.client.sign_in(
                phone,
                code,
                phone_code_hash=self._phone_code_hash
            )
            log.info('✅ Авторизация успешна')
            return True
        except SessionPasswordNeededError:
            # Требуется 2FA пароль
            raise RuntimeError('Требуется 2FA пароль (не поддерживается в этой версии)')
        except PhoneCodeInvalidError:
            raise ValueError('❌ Неверный код')
        except PhoneCodeExpiredError:
            raise ValueError('❌ Код истёк')
    
    async def connect(self):
        """Подключиться используя сохранённую сессию"""
        if not self.session_string:
            raise ValueError('Session string не установлен')
        
        self.client = TelegramClient(
            StringSession(self.session_string),
            API_ID,
            API_HASH
        )
        await self.client.connect()
        
        if not await self.client.is_user_authorized():
            await self.client.disconnect()
            self.client = None
            raise RuntimeError('Сессия недействительна или истекла')
        
        log.info('✅ Клиент подключён через StringSession')
        return True
    
    async def disconnect(self):
        """Отключиться от Telegram"""
        if self.client:
            await self.client.disconnect()
            self.client = None
            log.info('❌ Клиент отключён')
    
    async def get_session_string(self):
        """Получить StringSession для сохранения"""
        if self.client and await self.client.is_user_authorized():
            self.session_string = self.client.session.save()
            return self.session_string
        return None
    
    async def get_me(self):
        """Получить информацию о текущем пользователе"""
        if not self.client or not await self.client.is_user_authorized():
            return None
        
        me = await self.client.get_me()
        return {
            'user_id': me.id,
            'username': me.username,
            'first_name': me.first_name,
            'last_name': me.last_name,
            'phone': me.phone,
        }
    
    async def get_dialogs(self):
        """Получить список чатов/каналов"""
        if not self.client:
            raise RuntimeError('Клиент не подключён')
        
        dialogs = []
        async for dialog in self.client.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                entity = dialog.entity
                dialogs.append({
                    'chat_id': dialog.id,
                    'title': dialog.title or 'Без названия',
                    'username': getattr(entity, 'username', None),
                    'type': 'channel' if dialog.is_channel else 'group',
                    'participants_count': getattr(entity, 'participants_count', 0) or 0,
                })
        return dialogs
    
    async def iter_participants(self, chat_id, limit=None):
        """Итератор по участникам чата"""
        if not self.client:
            raise RuntimeError('Клиент не подключён')
        
        count = 0
        async for user in self.client.iter_participants(chat_id, limit=limit):
            if getattr(user, 'bot', False) or getattr(user, 'deleted', False):
                continue
            
            yield {
                'user_id': user.id,
                'username': getattr(user, 'username', None),
                'first_name': getattr(user, 'first_name', None),
                'last_name': getattr(user, 'last_name', None),
                'is_bot': bool(getattr(user, 'bot', False)),
                'access_hash': getattr(user, 'access_hash', None),
            }
            
            count += 1
            if limit is not None and count >= limit:
                break
    
    async def get_user_gifts(self, user_id: int, access_hash: int = None, limit: int = 1000):
        """
        Получить подарки пользователя через MTProto API
        
        Args:
            user_id: ID пользователя
            access_hash: Access hash пользователя
            limit: Максимальное количество подарков
        """
        if not self.client:
            raise RuntimeError('Клиент не подключён')
        
        if access_hash:
            peer = types.InputPeerUser(
                user_id=int(user_id),
                access_hash=int(access_hash)
            )
        else:
            peer = await self.client.get_input_entity(user_id)
        
        offset = ''
        result = []
        seen = set()
        
        while True:
            response = await self.client(
                functions.payments.GetSavedStarGiftsRequest(
                    peer=peer,
                    offset=offset,
                    limit=min(100, limit),
                    exclude_unsaved=False,
                    exclude_saved=False,
                    exclude_unlimited=False,
                    exclude_unique=False,
                    exclude_upgradable=False,
                    exclude_unupgradable=True,  # Исключаем обычные не-NFT подарки
                    exclude_hosted=False,
                )
            )
            
            gifts = getattr(response, 'gifts', None) or []
            for saved in gifts:
                data = self._normalize_gift(saved, user_id)
                key = (data.get('gift_id'), data.get('gift_num'))
                if key in seen:
                    continue
                seen.add(key)
                result.append(data)
                
                if len(result) >= limit:
                    return result
            
            next_offset = getattr(response, 'next_offset', None)
            if not next_offset or next_offset == offset or not gifts:
                break
            offset = next_offset
        
        return result
    
    def _normalize_gift(self, saved: Any, owner_id: int) -> dict:
        """Нормализовать данные подарка"""
        gift = getattr(saved, 'gift', None)
        gift_id = getattr(gift, 'id', None)
        title = getattr(gift, 'title', None)
        gift_num = getattr(saved, 'gift_num', None) or getattr(gift, 'num', None)
        slug = getattr(gift, 'slug', None)
        unique = isinstance(gift, types.StarGiftUnique)
        
        return {
            'gift_id': gift_id,
            'gift_num': gift_num,
            'gift_name': title or 'Telegram Gift',
            'gift_slug': slug,
            'is_collectible': unique,
            'can_upgrade': bool(getattr(saved, 'can_upgrade', False)),
            'owner_id': owner_id,
        }
    
    def is_connected(self):
        """Проверка подключения"""
        return bool(self.client and self.client.is_connected())
