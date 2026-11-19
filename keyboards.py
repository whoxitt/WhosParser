"""
Клавиатуры для главного бота
"""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def admin_menu():
    """Главное меню администратора"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='⚙️ Админка')],
            [KeyboardButton(text='🔎 Парсер')],
        ],
        resize_keyboard=True
    )


def admin_panel_menu(has_session: bool = False):
    """Меню админ-панели"""
    buttons = []
    
    if not has_session:
        buttons.append([InlineKeyboardButton(
            text='📱 Подключить аккаунт',
            callback_data='admin:connect_phone'
        )])
    else:
        buttons.append([InlineKeyboardButton(
            text='🔌 Отключить аккаунт',
            callback_data='admin:disconnect'
        )])
        buttons.append([InlineKeyboardButton(
            text='ℹ️ Информация об аккаунте',
            callback_data='admin:account_info'
        )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cancel_keyboard():
    """Кнопка отмены"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='❌ Отмена')]],
        resize_keyboard=True
    )
