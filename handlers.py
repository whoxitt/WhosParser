"""
Обработчики команд и callback'ов бота
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

import keyboards as kb
import ui
from database import DatabasePG
from ton_api import TonConsoleAPI
from parsing_scanner import ChatScanner
from parsing_telegram_client import ParserClient

log = logging.getLogger('handlers')

router = Router()

# Глобальные переменные (будут инициализированы в bot.py)
db: DatabasePG = None
ton_api: TonConsoleAPI = None
parser_client: ParserClient = None
OWNER_ID: int = 0

# Активные сессии парсинга {user_id: scanner}
active_parsers = {}


class BroadcastState(StatesGroup):
    waiting_message = State()


class AddChatState(StatesGroup):
    waiting_forward = State()


# ============== ОСНОВНЫЕ КОМАНДЫ ==============

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Команда /start"""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # Создаём/обновляем пользователя в БД
    db.get_or_create_user(user_id, username, first_name)
    
    # Проверяем подписку
    has_sub = db.has_active_subscription(user_id)
    
    await message.answer(
        ui.welcome_message(has_sub),
        reply_markup=kb.main_menu_kb(has_sub)
    )


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    """Вернуться в главное меню"""
    user_id = callback.from_user.id
    has_sub = db.has_active_subscription(user_id)
    
    await callback.message.edit_text(
        ui.welcome_message(has_sub),
        reply_markup=kb.main_menu_kb(has_sub)
    )
    await callback.answer()


@router.callback_query(F.data == "close")
async def close_message(callback: CallbackQuery):
    """Закрыть сообщение"""
    await callback.message.delete()
    await callback.answer()


# ============== ПОДПИСКА ==============

@router.callback_query(F.data == "buy_subscription")
async def buy_subscription(callback: CallbackQuery):
    """Покупка подписки"""
    user_id = callback.from_user.id
    
    # Создаём платёж
    memo = db.create_payment(user_id, 5.0)
    
    # Получаем адрес кошелька из переменных окружения
    wallet = ton_api.wallet_address
    
    await callback.message.edit_text(
        ui.buy_subscription_message(wallet, 5.0, memo),
        reply_markup=kb.check_payment_kb(memo)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("check_payment:"))
async def check_payment(callback: CallbackQuery):
    """Проверка платежа"""
    memo = callback.data.split(":", 1)[1]
    
    await callback.answer(ui.payment_checking_message())
    
    # Проверяем платёж через TON API
    payment = ton_api.check_payment(memo, amount=5.0)
    
    if payment:
        # Платёж найден
        payment_data = db.get_payment_by_memo(memo)
        if payment_data and payment_data['status'] == 'pending':
            # Активируем подписку
            db.complete_payment(memo, payment.get('tx_hash'))
            db.add_subscription(payment_data['user_id'], hours=24)
            
            await callback.message.edit_text(
                ui.payment_success_message(),
                reply_markup=kb.back_to_menu_kb()
            )
            
            log.info(f"Подписка активирована для user_id={payment_data['user_id']}")
        else:
            await callback.message.edit_text(
                "Подписка уже активирована ранее.",
                reply_markup=kb.back_to_menu_kb()
            )
    else:
        # Платёж не найден
        await callback.message.edit_text(
            ui.payment_not_found_message(),
            reply_markup=kb.check_payment_kb(memo)
        )


@router.callback_query(F.data == "subscription_info")
async def subscription_info(callback: CallbackQuery):
    """Информация о подписке"""
    user_id = callback.from_user.id
    until = db.get_subscription_until(user_id)
    
    await callback.message.edit_text(
        ui.subscription_info_message(until),
        reply_markup=kb.renew_subscription_kb() if not until or until < datetime.now() else kb.back_to_menu_kb()
    )
    await callback.answer()


# ============== ПРОФИЛЬ ==============

@router.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery):
    """Профиль пользователя"""
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    
    await callback.message.edit_text(
        ui.profile_message(user),
        reply_markup=kb.back_to_menu_kb()
    )
    await callback.answer()


# ============== ПАРСИНГ ==============

@router.callback_query(F.data == "start_parsing")
async def start_parsing(callback: CallbackQuery):
    """Начать парсинг"""
    user_id = callback.from_user.id
    
    # Проверка подписки
    if not db.has_active_subscription(user_id):
        await callback.answer(ui.no_subscription_message(), show_alert=True)
        return
    
    # Проверка кулдауна
    if not db.can_start_parsing(user_id, cooldown_minutes=5):
        last_time = db.get_last_parsing_time(user_id)
        if last_time:
            time_passed = datetime.now() - last_time
            seconds_left = (5 * 60) - int(time_passed.total_seconds())
            await callback.answer(ui.cooldown_message(seconds_left), show_alert=True)
            return
    
    # Проверка что парсинг уже не запущен
    if user_id in active_parsers:
        await callback.answer("Парсинг уже запущен", show_alert=True)
        return
    
    await callback.message.edit_text(
        ui.parsing_confirm_message(),
        reply_markup=kb.confirm_parsing_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "confirm_parsing")
async def confirm_parsing(callback: CallbackQuery):
    """Подтверждение и запуск парсинга"""
    user_id = callback.from_user.id
    
    # Проверка что parser_client подключён
    if not parser_client:
        await callback.message.edit_text("Парсер не подключён. Обратитесь к администратору.")
        await callback.answer()
        return
    
    progress_msg = await callback.message.edit_text("🔍 Инициализация парсинга...")
    
    # Переподключаем parser_client в текущем event loop
    try:
        if parser_client.client:
            await parser_client.disconnect()
        
        # Создаём новый клиент в текущем event loop
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        
        parser_client.client = TelegramClient(
            StringSession(parser_client.session_string),
            int(os.getenv('TG_API_ID', '2040')),
            os.getenv('TG_API_HASH', 'b18441a1ff607e10a989891a5462e627')
        )
        await parser_client.client.connect()
        
        if not await parser_client.client.is_user_authorized():
            await progress_msg.edit_text("Сессия парсера истекла. Обратитесь к администратору.")
            return
            
    except Exception as e:
        log.error(f"Ошибка переподключения parser_client: {e}")
        await progress_msg.edit_text("Ошибка подключения парсера.")
        return
    
    # Создаём сессию парсинга
    session_id = db.create_parser_session(user_id)
    
    # Получаем активные чаты (в рандомном порядке)
    chats = db.get_active_parser_chats()
    
    if not chats:
        await progress_msg.edit_text("Нет активных чатов для парсинга.")
        db.complete_parser_session(session_id, 0)
        return
    
    # Запускаем парсинг
    try:
        active_parsers[user_id] = True
        
        found_count = 0
        max_users = 10
        checked_count = 0
        start_time = datetime.now()
        
        await progress_msg.edit_text(f"🔍 Найдено: 0/{max_users}\n📊 Проверено: 0\n⏱ Время: 0 сек")
        
        # Проходим по рандомным чатам
        for chat_idx, chat in enumerate(chats):
            if found_count >= max_users:
                break
            
            chat_title = chat.get('title', 'Неизвестный чат')
            
            try:
                # Обновляем прогресс
                elapsed = int((datetime.now() - start_time).total_seconds())
                await progress_msg.edit_text(
                    f"🔍 Найдено: {found_count}/{max_users}\n"
                    f"📊 Проверено: {checked_count}\n"
                    f"💬 Чат: {chat_title[:30]}...\n"
                    f"⏱ Время: {elapsed} сек"
                )
                
                log.info(f"Начинаю парсинг чата {chat_title} (ID: {chat['chat_id']})")
                
                # Получаем пользователей из чата
                users_checked_in_chat = 0
                users_found_in_iterator = 0
                
                async for user_data in parser_client.iter_chat_users(chat['chat_id'], max_messages=5000):
                    users_found_in_iterator += 1
                    
                    if found_count >= max_users:
                        break
                    
                    user_id_to_check = user_data.get('user_id')
                    
                    # Пропускаем уже найденных глобально
                    if db.is_user_globally_seen(user_id_to_check):
                        continue
                    
                    checked_count += 1
                    users_checked_in_chat += 1
                    
                    # Обновляем прогресс каждые 5 пользователей
                    if checked_count % 5 == 0:
                        elapsed = int((datetime.now() - start_time).total_seconds())
                        await progress_msg.edit_text(
                            f"🔍 Найдено: {found_count}/{max_users}\n"
                            f"📊 Проверено: {checked_count}\n"
                            f"💬 Чат: {chat_title[:30]}...\n"
                            f"⏱ Время: {elapsed} сек"
                        )
                    
                    # Проверяем NFT
                    try:
                        gifts = await parser_client.get_user_gifts(
                            user_id_to_check, 
                            access_hash=user_data.get('access_hash'),
                            limit=1000,
                            only_unupgraded=False
                        )
                    except Exception as e:
                        log.debug(f"Ошибка получения подарков для {user_id_to_check}: {e}")
                        continue
                    
                    # Фильтруем NFT (can_upgrade=True ИЛИ is_collectible=True)
                    nft_gifts = [g for g in gifts if g.get('is_nft_candidate', False)]
                    
                    if nft_gifts:
                        # Нашли пользователя с NFT
                        found_user_id = db.add_found_nft_user(
                            session_id,
                            user_id_to_check,
                            user_data.get('username'),
                            user_data.get('first_name'),
                            chat['chat_id'],
                            chat_title,
                            len(nft_gifts)
                        )
                        
                        if found_user_id:
                            # Сохраняем подарки
                            for gift in nft_gifts:
                                db.add_nft_gift(
                                    found_user_id,
                                    gift.get('gift_id'),
                                    gift.get('gift_name'),
                                    gift.get('gift_slug'),
                                    gift.get('gift_num'),
                                    gift.get('can_upgrade', False),
                                    gift.get('is_collectible', False)
                                )
                            
                            # Отмечаем как найденного глобально
                            db.mark_user_globally_seen(user_id_to_check, user_id)
                            
                            found_count += 1
                            
                            # Сразу отправляем результат
                            try:
                                await send_nft_result(callback.message.chat.id, user_data, nft_gifts, chat_title, callback.bot)
                            except Exception as e:
                                log.error(f"Ошибка отправки результата: {e}")
                            
                            # Обновляем прогресс
                            elapsed = int((datetime.now() - start_time).total_seconds())
                            await progress_msg.edit_text(
                                f"✅ Найдено: {found_count}/{max_users}\n"
                                f"📊 Проверено: {checked_count}\n"
                                f"💬 Чат: {chat_title[:30]}...\n"
                                f"⏱ Время: {elapsed} сек"
                            )
                    
                    # Небольшая задержка между пользователями
                    await asyncio.sleep(0.3)
                    
                    # Если в этом чате проверили много и ничего не нашли - переходим к следующему
                    if users_checked_in_chat > 50 and found_count == 0:
                        break
                
                log.info(f"Завершил парсинг чата {chat_title}: найдено в итераторе={users_found_in_iterator}, проверено={users_checked_in_chat}")
                    
            except Exception as e:
                log.error(f"Ошибка парсинга чата {chat['chat_id']}: {e}")
                continue
        
        # Завершаем сессию
        db.complete_parser_session(session_id, found_count)
        
        elapsed = int((datetime.now() - start_time).total_seconds())
        await progress_msg.edit_text(
            f"✅ Парсинг завершён!\n\n"
            f"Найдено: {found_count}/{max_users}\n"
            f"Проверено: {checked_count} пользователей\n"
            f"Время: {elapsed} сек"
        )
        
    except Exception as e:
        log.exception(f"Ошибка парсинга для user_id={user_id}: {e}")
        await progress_msg.edit_text("Произошла ошибка при парсинге.")
        db.complete_parser_session(session_id, 0)
    finally:
        if user_id in active_parsers:
            del active_parsers[user_id]


async def send_nft_result(chat_id: int, user_data: dict, gifts: list, chat_title: str, bot):
    """Отправить результат найденного NFT"""
    user_id = user_data.get('user_id')
    username = user_data.get('username')
    first_name = user_data.get('first_name')
    
    # Валидация user_id
    if not user_id or not isinstance(user_id, int):
        log.error(f"Невалидный user_id: {user_id}")
        return
    
    if len(gifts) == 1:
        # Один NFT - показываем подробно
        gift = gifts[0]
        text = ui.nft_user_single_gift(
            username,
            first_name,
            user_id,
            gift.get('gift_name', 'Неизвестный'),
            gift.get('gift_num'),
            chat_title
        )
    else:
        # Несколько NFT - показываем количество
        text = ui.nft_user_multiple_gifts(
            username,
            first_name,
            user_id,
            len(gifts),
            chat_title
        )
    
    try:
        # Пробуем отправить с кнопкой
        await bot.send_message(chat_id, text, reply_markup=kb.open_profile_kb(user_id))
    except Exception as e:
        # Если ошибка с кнопкой - отправляем без неё
        log.warning(f"Ошибка отправки с кнопкой для user {user_id}: {e}")
        try:
            await bot.send_message(chat_id, text)
        except Exception as e2:
            log.error(f"Ошибка отправки сообщения: {e2}")


# ============== АДМИНКА ==============

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Админ-панель"""
    if message.from_user.id != OWNER_ID:
        return
    
    await message.answer(
        ui.admin_menu_message(),
        reply_markup=kb.admin_menu_kb()
    )


@router.message(Command("setup_parser"))
async def cmd_setup_parser(message: Message):
    """Информация о настройке парсера"""
    if message.from_user.id != OWNER_ID:
        return
    
    session = db.get_parser_session()
    
    if session and session.get('session_string'):
        status = "✅ Подключён"
        info = f"\nАккаунт: {session.get('first_name', 'N/A')}"
        if session.get('username'):
            info += f" (@{session['username']})"
    else:
        status = "❌ Не подключён"
        info = ""
    
    text = f"""<b>Парсер-аккаунт</b>

Статус: {status}{info}

<b>Как подключить:</b>

1. Нужен отдельный Telegram аккаунт (не бот!)
2. Этот аккаунт должен быть добавлен во все чаты для парсинга
3. Для подключения используйте отдельный скрипт setup_parser.py

<b>Инструкция:</b>
См. файл SETUP_PARSER.md в проекте

Или обратитесь к разработчику для настройки."""
    
    await message.answer(text)


@router.callback_query(F.data == "admin")
async def admin_menu(callback: CallbackQuery):
    """Главное меню админки"""
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    
    await callback.message.edit_text(
        ui.admin_menu_message(),
        reply_markup=kb.admin_menu_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    """Статистика"""
    if callback.from_user.id != OWNER_ID:
        return
    
    stats = db.get_admin_stats()
    
    await callback.message.edit_text(
        ui.admin_stats_message(stats),
        reply_markup=kb.admin_back_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_chats")
@router.callback_query(F.data.startswith("admin_chats_page:"))
async def admin_chats(callback: CallbackQuery):
    """Управление чатами"""
    if callback.from_user.id != OWNER_ID:
        return
    
    # Получаем страницу
    page = 0
    if ":" in callback.data:
        page = int(callback.data.split(":")[1])
    
    chats = db.get_all_parser_chats()
    active_count = len([c for c in chats if c.get('is_active', False)])
    
    await callback.message.edit_text(
        ui.admin_chats_message(len(chats), active_count),
        reply_markup=kb.admin_chats_kb(chats, page)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_chat:"))
async def toggle_chat(callback: CallbackQuery):
    """Переключить чат"""
    if callback.from_user.id != OWNER_ID:
        return
    
    parts = callback.data.split(":")
    chat_id = int(parts[1])
    page = int(parts[2])
    
    db.toggle_parser_chat(chat_id)
    
    # Обновляем список (остаёмся на той же странице)
    chats = db.get_all_parser_chats()
    active_count = len([c for c in chats if c.get('is_active', False)])
    
    await callback.message.edit_text(
        ui.admin_chats_message(len(chats), active_count),
        reply_markup=kb.admin_chats_kb(chats, page)
    )
    await callback.answer("Статус изменён")


@router.callback_query(F.data == "add_chat")
async def add_chat_start(callback: CallbackQuery, state: FSMContext):
    """Начать добавление чата"""
    if callback.from_user.id != OWNER_ID:
        return
    
    await callback.message.answer(ui.admin_add_chat_message())
    await state.set_state(AddChatState.waiting_forward)
    await callback.answer()


@router.message(AddChatState.waiting_forward)
async def add_chat_forward(message: Message, state: FSMContext):
    """Обработка пересланного сообщения"""
    if message.from_user.id != OWNER_ID:
        return
    
    if message.forward_from_chat:
        chat = message.forward_from_chat
        db.add_parser_chat(chat.id, chat.title, chat.username)
        
        await message.answer(ui.admin_chat_added_message(chat.title))
        await state.clear()
    else:
        await message.answer("Перешлите сообщение из чата.")


@router.callback_query(F.data == "admin_users")
@router.callback_query(F.data.startswith("admin_users_page:"))
async def admin_users(callback: CallbackQuery):
    """Список пользователей"""
    if callback.from_user.id != OWNER_ID:
        return
    
    page = 0
    if ":" in callback.data:
        page = int(callback.data.split(":")[1])
    
    users = db.get_all_users()
    
    await callback.message.edit_text(
        ui.admin_users_message(len(users)),
        reply_markup=kb.admin_users_kb(users, page)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_user:"))
async def admin_user_info(callback: CallbackQuery):
    """Информация о пользователе"""
    if callback.from_user.id != OWNER_ID:
        return
    
    user_id = int(callback.data.split(":")[1])
    user = db.get_user(user_id)
    
    if user:
        await callback.message.edit_text(
            ui.admin_user_info_message(user),
            reply_markup=kb.admin_user_actions_kb(user_id)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("grant_sub:"))
async def grant_subscription(callback: CallbackQuery):
    """Выдать подписку"""
    if callback.from_user.id != OWNER_ID:
        return
    
    user_id = int(callback.data.split(":")[1])
    db.add_subscription(user_id, hours=24)
    
    await callback.answer(ui.subscription_granted_message(), show_alert=True)


@router.callback_query(F.data.startswith("reset_cooldown:"))
async def reset_cooldown(callback: CallbackQuery):
    """Сбросить кулдаун (реализуется через обнуление last_parsing_at)"""
    if callback.from_user.id != OWNER_ID:
        return
    
    # Простая реализация - можно расширить
    await callback.answer(ui.cooldown_reset_message(), show_alert=True)


@router.callback_query(F.data == "admin_payments")
@router.callback_query(F.data.startswith("admin_payments_page:"))
async def admin_payments(callback: CallbackQuery):
    """Список платежей"""
    if callback.from_user.id != OWNER_ID:
        return
    
    page = 0
    if ":" in callback.data:
        page = int(callback.data.split(":")[1])
    
    payments = db.get_all_payments()
    per_page = 10
    start = page * per_page
    end = start + per_page
    
    await callback.message.edit_text(
        ui.admin_payments_message(payments[start:end], page),
        reply_markup=kb.admin_payments_kb(page)
    )
    await callback.answer()


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    """Начать рассылку"""
    if callback.from_user.id != OWNER_ID:
        return
    
    await callback.message.answer(ui.admin_broadcast_message())
    await state.set_state(BroadcastState.waiting_message)
    await callback.answer()


@router.message(BroadcastState.waiting_message)
async def admin_broadcast_message(message: Message, state: FSMContext):
    """Получение сообщения для рассылки"""
    if message.from_user.id != OWNER_ID:
        return
    
    if message.text == "/cancel":
        await message.answer("Рассылка отменена.")
        await state.clear()
        return
    
    # Сохраняем сообщение
    await state.update_data(broadcast_text=message.text)
    
    users = db.get_all_users()
    
    await message.answer(
        ui.admin_broadcast_confirm_message(len(users)),
        reply_markup=kb.confirm_broadcast_kb()
    )


@router.callback_query(F.data == "confirm_broadcast")
async def admin_broadcast_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и отправка рассылки"""
    if callback.from_user.id != OWNER_ID:
        return
    
    data = await state.get_data()
    text = data.get('broadcast_text')
    
    users = db.get_all_users()
    
    success = 0
    failed = 0
    
    for user in users:
        try:
            await callback.bot.send_message(user['user_id'], text)
            success += 1
            await asyncio.sleep(0.05)  # Антифлуд
        except:
            failed += 1
    
    await callback.message.edit_text(ui.admin_broadcast_completed_message(success, failed))
    await state.clear()
    await callback.answer()


def setup_handlers(dp, database: DatabasePG, ton_console: TonConsoleAPI, parser: ParserClient, owner_id: int):
    """Инициализация хэндлеров"""
    global db, ton_api, parser_client, OWNER_ID
    db = database
    ton_api = ton_console
    parser_client = parser
    OWNER_ID = owner_id
    
    dp.include_router(router)


def update_parser_client(new_parser_client: ParserClient):
    """Обновить parser client (для переподключения)"""
    global parser_client
    parser_client = new_parser_client
