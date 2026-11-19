"""
UI сообщения для бота
"""


def esc(text):
    """Экранирование HTML символов"""
    if not text:
        return ''
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def admin_welcome():
    """Приветственное сообщение для администратора"""
    return (
        '👋 <b>Добро пожаловать, администратор!</b>\n\n'
        '🔎 <b>Парсер NFT подарков</b>\n'
        'Бот для поиска пользователей с Telegram NFT подарками в чатах.\n\n'
        '⚙️ <b>Функции:</b>\n'
        '• Подключение Telegram-аккаунта через номер телефона\n'
        '• Парсинг участников из ваших чатов\n'
        '• Поиск пользователей с NFT\n'
        '• Фильтрация по неулучшенным подаркам\n\n'
        'Выберите действие в меню ниже:'
    )


def user_welcome():
    """Сообщение для обычных пользователей"""
    return (
        'ℹ️ <b>Доступ ограничен</b>\n\n'
        'Этот бот доступен только администратору.'
    )


def admin_panel(session):
    """Админ-панель"""
    if session and session.get('is_active'):
        username = session.get('username') or 'без username'
        user_id = session.get('user_id', 'н/д')
        phone = session.get('phone', 'н/д')
        
        return (
            '⚙️ <b>АДМИН-ПАНЕЛЬ</b>\n\n'
            '✅ <b>Аккаунт подключён</b>\n'
            f'👤 @{username}\n'
            f'🆔 <code>{user_id}</code>\n'
            f'📱 <code>{phone}</code>\n\n'
            '🔄 Сессия сохранена. При перезапуске бота подключение восстановится автоматически.'
        )
    else:
        return (
            '⚙️ <b>АДМИН-ПАНЕЛЬ</b>\n\n'
            '🔴 <b>Аккаунт не подключён</b>\n\n'
            'Для работы парсера необходимо подключить ваш Telegram-аккаунт.\n'
            'Авторизация происходит через номер телефона с подтверждением кодом.'
        )


def parser_menu(session):
    """Меню парсера"""
    if session and session.get('is_active'):
        username = session.get('username') or 'без username'
        return (
            '🔎 <b>ПАРСЕР NFT ПОДАРКОВ</b>\n\n'
            '🟢 <b>Аккаунт подключён</b>\n'
            f'👤 @{username}\n'
            f'🆔 <code>{session.get("user_id")}</code>\n\n'
            'Парсер готов к работе. Выберите действие:'
        )
    else:
        return (
            '🔎 <b>ПАРСЕР NFT ПОДАРКОВ</b>\n\n'
            '🔴 <b>Аккаунт не подключён</b>\n\n'
            'Сначала подключите аккаунт через <b>⚙️ Админку</b>'
        )
