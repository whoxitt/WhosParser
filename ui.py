"""
UI сообщения бота
"""
from datetime import datetime


def format_time_left(until: datetime) -> str:
    """Форматировать оставшееся время"""
    if not until or until < datetime.now():
        return "Подписка истекла"
    
    delta = until - datetime.now()
    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)
    
    if hours > 24:
        days = hours // 24
        return f"{days} дн."
    elif hours > 0:
        return f"{hours} ч. {minutes} мин."
    else:
        return f"{minutes} мин."


def welcome_message(has_subscription: bool) -> str:
    """Приветственное сообщение"""
    return "<b>Привет, выбери действие</b>"


def buy_subscription_message(wallet: str, amount: float, memo: str) -> str:
    """Сообщение о покупке подписки"""
    return f"""<b>Покупка подписки</b>

Отправьте <b>{amount} TON</b> на адрес:
<code>{wallet}</code>

Обязательно укажите комментарий:
<code>{memo}</code>

После отправки нажмите "Проверить платёж"

Подписка активируется на 24 часа."""


def payment_checking_message() -> str:
    """Сообщение о проверке платежа"""
    return "⏳ Проверяю платёж..."


def payment_success_message() -> str:
    """Успешная оплата"""
    return "<b>Подписка активирована!</b>\n\nТеперь вы можете пользоваться парсингом."


def payment_not_found_message() -> str:
    """Платёж не найден"""
    return "Платёж не найден. Убедитесь что вы отправили правильную сумму с указанным комментарием."


def subscription_info_message(until: datetime) -> str:
    """Информация о подписке"""
    time_left = format_time_left(until)
    
    if until and until > datetime.now():
        return f"""<b>Действующая подписка</b>

Активна до: {until.strftime('%d.%m.%Y %H:%M')}
Осталось: {time_left}"""
    else:
        return "<b>Подписка истекла</b>\n\nПродлите подписку для продолжения работы."


def profile_message(user: dict) -> str:
    """Профиль пользователя"""
    subscription_status = "Активна" if user.get('subscription_until') and user['subscription_until'] > datetime.now() else "Неактивна"
    
    if user.get('subscription_until') and user['subscription_until'] > datetime.now():
        subscription_info = f"до {user['subscription_until'].strftime('%d.%m.%Y %H:%M')}"
    else:
        subscription_info = "-"
    
    return f"""<b>Ваш профиль</b>

Подписка: {subscription_status} {subscription_info}
Использовано парсингов: {user.get('total_parsings', 0)}
Найдено NFT: {user.get('total_found_nft', 0)}"""


def no_subscription_message() -> str:
    """Нет подписки"""
    return "У вас нет активной подписки. Купите доступ для использования парсинга."


def parsing_confirm_message() -> str:
    """Подтверждение парсинга"""
    return """<b>Запустить парсинг?</b>

Будет найдено до 10 пользователей с NFT подарками.
После завершения следующий парсинг можно будет запустить через 5 минут."""


def parsing_started_message() -> str:
    """Парсинг запущен"""
    return "Парсинг запущен. Ищу пользователей с NFT..."


def parsing_in_progress_message(found: int) -> str:
    """Парсинг в процессе"""
    return f"Найдено пользователей: {found}/10"


def parsing_completed_message(found: int) -> str:
    """Парсинг завершён"""
    if found == 0:
        return "Парсинг завершён. К сожалению, пользователи с NFT не найдены."
    else:
        return f"Парсинг завершён. Найдено пользователей: {found}"


def cooldown_message(seconds_left: int) -> str:
    """Кулдаун между парсингами"""
    minutes = int(seconds_left // 60)
    secs = int(seconds_left % 60)
    return f"Следующий парсинг можно запустить через {minutes} мин. {secs} сек."


def nft_user_single_gift(username: str, first_name: str, user_id: int, gift_name: str, gift_num: int, chat_title: str) -> str:
    """Найден пользователь с 1 NFT"""
    name = f"@{username}" if username else (first_name or f"ID: {user_id}")
    gift_number = f"#{gift_num}" if gift_num else ""
    
    return f"""<b>NFT Подарок</b>

Название: {gift_name}
Номер: {gift_number}
Владелец: {name}
Чат: {chat_title}"""


def nft_user_multiple_gifts(username: str, first_name: str, user_id: int, nft_count: int, chat_title: str) -> str:
    """Найден пользователь с несколькими NFT"""
    name = f"@{username}" if username else (first_name or f"ID: {user_id}")
    
    return f"""<b>Найден владелец NFT</b>

Владелец: {name}
Количество NFT: {nft_count}
Чат: {chat_title}"""


# ============== АДМИНКА ==============

def admin_menu_message() -> str:
    """Главное меню админки"""
    return "<b>Админ-панель</b>\n\nВыберите действие:"


def admin_stats_message(stats: dict) -> str:
    """Статистика админки"""
    return f"""<b>📊 Статистика</b>

Всего пользователей: {stats.get('total_users', 0)}
Активных подписок: {stats.get('active_subscriptions', 0)}
Всего парсингов: {stats.get('total_parsings', 0)}
Найдено NFT: {stats.get('total_found_nft', 0) or 0}
Доход: {stats.get('total_revenue', 0) or 0} TON
Активных чатов: {stats.get('active_chats', 0)}"""


def admin_chats_message(total: int, active: int) -> str:
    """Управление чатами"""
    return f"""<b>💬 Управление чатами</b>

Всего чатов: {total}
Активных: {active}

Выберите чат для включения/отключения:"""


def admin_users_message(total: int) -> str:
    """Список пользователей"""
    return f"""<b>👥 Пользователи</b>

Всего пользователей: {total}

Выберите пользователя:"""


def admin_user_info_message(user: dict) -> str:
    """Информация о пользователе"""
    username = f"@{user.get('username')}" if user.get('username') else f"ID: {user['user_id']}"
    subscription = "Активна" if user.get('subscription_until') and user['subscription_until'] > datetime.now() else "Неактивна"
    
    if user.get('subscription_until'):
        sub_info = f"до {user['subscription_until'].strftime('%d.%m.%Y %H:%M')}" if user['subscription_until'] > datetime.now() else "истекла"
    else:
        sub_info = "не было"
    
    return f"""<b>Информация о пользователе</b>

Пользователь: {username}
Имя: {user.get('first_name', 'Не указано')}
Подписка: {subscription} ({sub_info})
Парсингов: {user.get('total_parsings', 0)}
Найдено NFT: {user.get('total_found_nft', 0)}
Зарегистрирован: {user['created_at'].strftime('%d.%m.%Y %H:%M') if user.get('created_at') else 'Неизвестно'}"""


def admin_payments_message(payments: list, page: int = 0) -> str:
    """Список платежей"""
    if not payments:
        return "<b>💳 Платежи</b>\n\nПлатежей пока нет."
    
    text = f"<b>💳 Платежи (страница {page + 1})</b>\n\n"
    
    for payment in payments:
        status = "✅" if payment['status'] == 'completed' else "⏳"
        user_id = payment.get('user_id', 'N/A')
        amount = payment.get('amount', 0)
        created = payment['created_at'].strftime('%d.%m %H:%M') if payment.get('created_at') else 'N/A'
        
        text += f"{status} {amount} TON | User: {user_id}\n"
        text += f"   Memo: <code>{payment['memo']}</code>\n"
        text += f"   {created}\n\n"
    
    return text


def admin_broadcast_message() -> str:
    """Рассылка"""
    return """<b>📨 Рассылка</b>

Отправьте сообщение, которое хотите разослать всем пользователям.

Используйте команду /cancel для отмены."""


def admin_broadcast_confirm_message(users_count: int) -> str:
    """Подтверждение рассылки"""
    return f"<b>Подтвердите рассылку</b>\n\nСообщение будет отправлено {users_count} пользователям."


def admin_broadcast_completed_message(success: int, failed: int) -> str:
    """Рассылка завершена"""
    return f"<b>Рассылка завершена</b>\n\nУспешно: {success}\nОшибок: {failed}"


def admin_add_chat_message() -> str:
    """Добавление чата"""
    return """<b>➕ Добавить чат</b>

Перешлите любое сообщение из чата, который хотите добавить для парсинга.

Или отправьте /cancel для отмены."""


def admin_chat_added_message(title: str) -> str:
    """Чат добавлен"""
    return f"<b>Чат добавлен</b>\n\n{title}"


def subscription_granted_message() -> str:
    """Подписка выдана"""
    return "Подписка выдана на 24 часа."


def cooldown_reset_message() -> str:
    """Кулдаун сброшен"""
    return "Кулдаун сброшен. Пользователь может запустить парсинг."
