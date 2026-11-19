"""
Клавиатуры для бота
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


# ============== ГЛАВНОЕ МЕНЮ ==============

def main_menu_kb(has_subscription: bool) -> InlineKeyboardMarkup:
    """Главное меню"""
    buttons = []
    
    if not has_subscription:
        buttons.append([InlineKeyboardButton(text="Купить доступ (5 TON)", callback_data="buy_subscription")])
    else:
        buttons.append([
            InlineKeyboardButton(text="Парсинг", callback_data="start_parsing"),
            InlineKeyboardButton(text="Подписка", callback_data="subscription_info")
        ])
    
    buttons.append([InlineKeyboardButton(text="Профиль", callback_data="profile")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_to_menu_kb() -> InlineKeyboardMarkup:
    """Кнопка назад в меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад в меню", callback_data="back_to_menu")]
    ])


# ============== ПОДПИСКА ==============

def check_payment_kb(memo: str) -> InlineKeyboardMarkup:
    """Кнопка проверки платежа"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Проверить платёж", callback_data=f"check_payment:{memo}")],
        [InlineKeyboardButton(text="« Назад в меню", callback_data="back_to_menu")]
    ])


def renew_subscription_kb() -> InlineKeyboardMarkup:
    """Кнопка продления подписки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Продлить подписку", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="« Назад в меню", callback_data="back_to_menu")]
    ])


# ============== ПАРСИНГ ==============

def confirm_parsing_kb() -> InlineKeyboardMarkup:
    """Подтверждение запуска парсинга"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Запустить парсинг", callback_data="confirm_parsing")],
        [InlineKeyboardButton(text="Отмена", callback_data="back_to_menu")]
    ])


def open_profile_kb(user_id: int) -> InlineKeyboardMarkup:
    """Кнопка перехода в профиль пользователя"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Перейти в профиль", url=f"tg://user?id={user_id}")]
    ])


# ============== АДМИНКА ==============

def admin_menu_kb() -> InlineKeyboardMarkup:
    """Главное меню админки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💳 Платежи", callback_data="admin_payments")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="💬 Управление чатами", callback_data="admin_chats")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings")],
        [InlineKeyboardButton(text="📨 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="« Закрыть", callback_data="close")]
    ])


def admin_back_kb() -> InlineKeyboardMarkup:
    """Кнопка назад в админку"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад в админку", callback_data="admin")]
    ])


def admin_chats_kb(chats: list, page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    """Список чатов для управления"""
    buttons = []
    
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_chats = chats[start_idx:end_idx]
    
    for chat in page_chats:
        status = "✅" if chat.get('is_active', False) else "❌"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status} {chat['title'][:40]}", 
                callback_data=f"toggle_chat:{chat['chat_id']}:{page}"
            )
        ])
    
    # Навигация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="« Назад", callback_data=f"admin_chats_page:{page-1}"))
    if end_idx < len(chats):
        nav_buttons.append(InlineKeyboardButton(text="Вперёд »", callback_data=f"admin_chats_page:{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # Добавить новый чат
    buttons.append([InlineKeyboardButton(text="➕ Добавить чат", callback_data="add_chat")])
    buttons.append([InlineKeyboardButton(text="« Назад в админку", callback_data="admin")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_users_kb(users: list, page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    """Список пользователей"""
    buttons = []
    
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_users = users[start_idx:end_idx]
    
    for user in page_users:
        username = f"@{user['username']}" if user.get('username') else f"ID: {user['user_id']}"
        buttons.append([
            InlineKeyboardButton(
                text=username, 
                callback_data=f"admin_user:{user['user_id']}"
            )
        ])
    
    # Навигация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="« Назад", callback_data=f"admin_users_page:{page-1}"))
    if end_idx < len(users):
        nav_buttons.append(InlineKeyboardButton(text="Вперёд »", callback_data=f"admin_users_page:{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton(text="« Назад в админку", callback_data="admin")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_user_actions_kb(user_id: int) -> InlineKeyboardMarkup:
    """Действия с пользователем"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Выдать подписку", callback_data=f"grant_sub:{user_id}")],
        [InlineKeyboardButton(text="🔄 Сбросить кулдаун", callback_data=f"reset_cooldown:{user_id}")],
        [InlineKeyboardButton(text="« Назад", callback_data="admin_users")]
    ])


def admin_payments_kb(page: int = 0) -> InlineKeyboardMarkup:
    """Навигация по платежам"""
    buttons = []
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="« Назад", callback_data=f"admin_payments_page:{page-1}"))
    nav_buttons.append(InlineKeyboardButton(text="Вперёд »", callback_data=f"admin_payments_page:{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton(text="« Назад в админку", callback_data="admin")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def close_kb() -> InlineKeyboardMarkup:
    """Кнопка закрыть"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Закрыть", callback_data="close")]
    ])


def confirm_broadcast_kb() -> InlineKeyboardMarkup:
    """Подтверждение рассылки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить рассылку", callback_data="confirm_broadcast")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin")]
    ])
