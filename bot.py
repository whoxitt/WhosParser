"""
Telegram бот для парсинга NFT подарков из чатов
Версия: Clean Parser Only (PostgreSQL)
"""
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery
from dotenv import load_dotenv

import keyboards as kb
import ui
from database import DatabasePG
from parsing_telegram_client import ParserClient
from parsing_scanner import ChatScanner
import parsing_keyboards as parser_kb
import parsing_handlers as parser_handlers

load_dotenv()

# Настройка логирования
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/parser.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('parser')

# Загрузка переменных окружения
TOKEN = os.getenv('BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', '8564624250') or 0)

# PostgreSQL настройки
DATABASE_URL = os.getenv('DATABASE_URL')  # для bothost.ru

if not TOKEN:
    raise RuntimeError('❌ BOT_TOKEN не указан в переменных окружения')

if not DATABASE_URL:
    raise RuntimeError('❌ DATABASE_URL не указан в переменных окружения')

# Инициализация
bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
db = DatabasePG(DATABASE_URL)

# Подключаем router парсера
dp.include_router(parser_handlers.router)

# Глобальные переменные для парсера
parser_client = None
scanner = None
scan_task = None

log.info('🚀 Бот запущен. OWNER_ID=%s', OWNER_ID)


class AdminStates(StatesGroup):
    """Состояния для админ-панели"""
    waiting_phone = State()
    waiting_code = State()


def is_admin(user_id: int) -> bool:
    """Проверка прав администратора"""
    return user_id == OWNER_ID


# ============== MIDDLEWARE ==============

@dp.message.middleware()
@dp.callback_query.middleware()
async def inject_db(handler, event, data):
    """Внедряем БД в каждый handler"""
    data['db'] = db
    return await handler(event, data)


# ============== БАЗОВЫЕ КОМАНДЫ ==============

@dp.message(Command('start'))
async def start_command(m: Message, state: FSMContext):
    """Команда /start"""
    await state.clear()
    if is_admin(m.from_user.id):
        await m.answer(ui.admin_welcome(), reply_markup=kb.admin_menu())
    else:
        await m.answer(ui.user_welcome())


@dp.message(Command('menu'))
async def menu_command(m: Message):
    """Команда /menu"""
    if is_admin(m.from_user.id):
        await m.answer('📋 Главное меню:', reply_markup=kb.admin_menu())
    else:
        await m.answer('ℹ️ Этот бот доступен только администратору.')


# ============== АДМИН-ПАНЕЛЬ ==============

@dp.message(F.text == '⚙️ Админка')
async def admin_panel(m: Message, db):
    """Админ-панель"""
    if not is_admin(m.from_user.id):
        return await m.answer('🚫 Доступ запрещён')
    
    session = db.get_parser_session()
    await m.answer(ui.admin_panel(session), reply_markup=kb.admin_panel_menu(bool(session)))


@dp.callback_query(F.data == 'admin:connect_phone')
async def admin_connect_phone(c: CallbackQuery, state: FSMContext):
    """Начало подключения аккаунта через номер телефона"""
    if not is_admin(c.from_user.id):
        return await c.answer('🚫 Доступ запрещён', show_alert=True)
    
    await state.set_state(AdminStates.waiting_phone)
    await c.message.answer(
        '📱 <b>ПОДКЛЮЧЕНИЕ АККАУНТА</b>\n\n'
        'Введите номер телефона в международном формате:\n'
        'Пример: <code>+79991234567</code>',
        reply_markup=kb.cancel_keyboard()
    )
    await c.answer()


@dp.message(AdminStates.waiting_phone)
async def admin_phone_input(m: Message, state: FSMContext):
    """Обработка ввода номера телефона"""
    if not is_admin(m.from_user.id):
        return
    
    if m.text == '❌ Отмена':
        await state.clear()
        return await m.answer('Отменено', reply_markup=kb.admin_menu())
    
    phone = m.text.strip()
    if not phone.startswith('+') or len(phone) < 10:
        return await m.answer('❌ Неверный формат. Пример: <code>+79991234567</code>')
    
    try:
        # Создаём клиент и отправляем код
        global parser_client
        parser_client = ParserClient()  # Создаём БЕЗ сессии
        await parser_client.send_code(phone)
        
        await state.update_data(phone=phone)
        await state.set_state(AdminStates.waiting_code)
        
        await m.answer(
            '✅ Код отправлен на ваш Telegram\n\n'
            '🔐 Введите код <b>через пробелы</b>:\n'
            'Пример: <code>1 2 3 4 5</code>',
            reply_markup=kb.cancel_keyboard()
        )
    except Exception as e:
        log.exception('Ошибка отправки кода')
        await m.answer(f'❌ Ошибка: {str(e)}')
        await state.clear()


@dp.message(AdminStates.waiting_code)
async def admin_code_input(m: Message, state: FSMContext, db):
    """Обработка ввода кода подтверждения"""
    if not is_admin(m.from_user.id):
        return
    
    if m.text == '❌ Отмена':
        await state.clear()
        global parser_client
        if parser_client:
            await parser_client.disconnect()
            parser_client = None
        return await m.answer('Отменено', reply_markup=kb.admin_menu())
    
    # Убираем пробелы из кода
    code = m.text.strip().replace(' ', '')
    
    if not code.isdigit() or len(code) < 5:
        return await m.answer(
            '❌ Неверный формат кода\n\n'
            'Введите код <b>через пробелы</b>:\n'
            'Пример: <code>1 2 3 4 5</code>'
        )
    
    data = await state.get_data()
    phone = data.get('phone')
    
    try:
        # Подтверждаем код и получаем сессию
        await parser_client.sign_in(phone, code)
        session_string = await parser_client.get_session_string()
        me = await parser_client.get_me()
        
        if not session_string or not me:
            raise RuntimeError('Не удалось получить данные аккаунта')
        
        # Сохраняем в БД
        db.save_parser_session(
            owner_id=m.from_user.id,
            session_string=session_string,
            phone=phone,
            username=me.get('username'),
            user_id=me.get('user_id'),
            first_name=me.get('first_name')
        )
        
        await state.clear()
        await m.answer(
            '✅ <b>АККАУНТ ПОДКЛЮЧЁН</b>\n\n'
            f'👤 @{me.get("username") or "без username"}\n'
            f'🆔 <code>{me.get("user_id")}</code>\n\n'
            '🔄 Сессия сохранена. При перезапуске бота подключение восстановится автоматически.',
            reply_markup=kb.admin_menu()
        )
        
        log.info('✅ Парсер-аккаунт подключён: @%s', me.get('username'))
        
    except Exception as e:
        log.exception('Ошибка авторизации')
        await m.answer(
            f'❌ Ошибка авторизации:\n<code>{str(e)}</code>\n\n'
            'Попробуйте ещё раз или проверьте правильность кода.'
        )


# ============== ПАРСЕР ==============

@dp.message(F.text == '🔎 Парсер')
async def parser_menu(m: Message, db):
    """Меню парсера"""
    if not is_admin(m.from_user.id):
        return await m.answer('🚫 Доступ запрещён')
    
    if not parser_handlers._parser_access_allowed(db, m.from_user.id):
        return await m.answer('🔒 Доступ к парсеру запрещён.')
    session = db.get_parser_session()
    is_connected = bool(session and session.get('is_active'))
    await m.answer(
        parser_handlers.format_parser_menu(session),
        reply_markup=parser_kb.parser_main_menu(is_connected),
    )




@dp.callback_query(F.data == 'admin:account_info')
async def admin_account_info(c: CallbackQuery, db):
    if not is_admin(c.from_user.id):
        return await c.answer('🚫 Доступ запрещён', show_alert=True)
    session = db.get_parser_session()
    if not session:
        return await c.answer('Аккаунт не подключён', show_alert=True)
    info = (
        'ℹ️ <b>Аккаунт парсера</b>\\n\\n'
        f'👤 @{session.get("username") or "без username"}\\n'
        f'🆔 <code>{session.get("user_id") or "—"}</code>\\n'
        f'📱 <code>{session.get("phone") or "—"}</code>\\n'
        f'🟢 Активен: <b>{"да" if session.get("is_active") else "нет"}</b>'
    )
    await c.message.answer(info)
    await c.answer()


@dp.callback_query(F.data == 'admin:disconnect')
async def admin_disconnect(c: CallbackQuery, db):
    if not is_admin(c.from_user.id):
        return await c.answer('🚫 Доступ запрещён', show_alert=True)
    try:
        if parser_handlers.parser_client:
            await parser_handlers.parser_client.disconnect()
            parser_handlers.parser_client = None
        db.clear_parser_session()
        await c.message.edit_text('🚪 Аккаунт парсера отключён.')
        await c.answer('Отключено')
    except Exception as exc:
        log.exception('Admin disconnect failed')
        await c.answer(f'Ошибка: {str(exc)[:150]}', show_alert=True)


# ============== ЗАПУСК БОТА ==============

async def restore_session_on_startup():
    """Автоматическое восстановление сессии при запуске"""
    try:
        session = db.get_parser_session()
        if session and session.get('session_string'):
            global parser_client
            parser_client = ParserClient(session['session_string'])
            await parser_client.connect()
            log.info('✅ Сессия парсера восстановлена автоматически')
    except Exception as e:
        log.warning('⚠️ Не удалось восстановить сессию: %s', e)


async def main():
    """Главная функция запуска"""
    log.info('🔄 Инициализация базы данных...')
    db.init_tables()
    
    log.info('🔄 Восстановление сессии...')
    await parser_handlers.restore_saved_parser_session(db)
    
    log.info('✅ Бот запущен и готов к работе')
    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info('👋 Бот остановлен')
