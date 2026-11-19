"""
Telegram бот для парсинга NFT подарков
Многопользовательский режим с подписками через TON
"""
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from database import DatabasePG
from ton_api import TonConsoleAPI
from parsing_telegram_client import ParserClient
import handlers

load_dotenv()

# Настройка логирования
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('bot')

# Переменные окружения
TOKEN = os.getenv('BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', 0) or 0)
DATABASE_URL = os.getenv('DATABASE_URL')
TON_API_KEY = os.getenv('TON_API_KEY')
TON_WALLET_ADDRESS = os.getenv('TON_WALLET_ADDRESS')

if not TOKEN:
    raise RuntimeError('BOT_TOKEN не указан в переменных окружения')

if not DATABASE_URL:
    raise RuntimeError('DATABASE_URL не указан в переменных окружения')

if not TON_API_KEY or not TON_WALLET_ADDRESS:
    log.warning('TON_API_KEY или TON_WALLET_ADDRESS не указаны - платежи работать не будут')

# Инициализация
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# База данных
db = DatabasePG(DATABASE_URL)
db.init_tables()

# TON API
ton_api = TonConsoleAPI(TON_API_KEY or '', TON_WALLET_ADDRESS or '')

# Parser Client (будет инициализирован в async контексте)
parser_client = None


async def init_parser_client():
    """Инициализация parser client в правильном event loop"""
    global parser_client
    
    parser_session = db.get_parser_session()
    
    if parser_session and parser_session.get('session_string'):
        try:
            parser_client = ParserClient(parser_session['session_string'])
            await parser_client.connect()
            log.info('Parser client подключён')
        except Exception as e:
            log.error(f'Ошибка подключения parser client: {e}')
            parser_client = None


async def shutdown_parser_client():
    """Отключение parser client"""
    if parser_client:
        try:
            await parser_client.disconnect()
        except:
            pass


async def main():
    """Запуск бота"""
    log.info('Бот запущен')
    
    # Инициализируем parser client в правильном event loop
    await init_parser_client()
    
    # Подключаем обработчики после инициализации parser_client
    handlers.setup_handlers(dp, db, ton_api, parser_client, OWNER_ID)
    
    try:
        await dp.start_polling(bot)
    finally:
        await shutdown_parser_client()
        await bot.session.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info('Бот остановлен')
