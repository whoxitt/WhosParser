"""
Скрипт для настройки парсер-аккаунта
Запустите локально: python setup_parser.py
"""
import asyncio
import os
from dotenv import load_dotenv
from parsing_telegram_client import ParserClient
from database import DatabasePG

load_dotenv()


async def main():
    print("=" * 50)
    print("НАСТРОЙКА ПАРСЕР-АККАУНТА")
    print("=" * 50)
    print()
    print("⚠️  ВАЖНО:")
    print("- Используйте ОТДЕЛЬНЫЙ Telegram аккаунт (не бот!)")
    print("- Этот аккаунт должен быть добавлен во все чаты для парсинга")
    print("- Желательно Premium аккаунт для лучшего доступа")
    print()
    
    phone = input("Введите номер телефона (например, +79991234567): ").strip()
    
    if not phone.startswith('+'):
        print("❌ Номер должен начинаться с +")
        return
    
    print("\n🔄 Отправляю код...")
    
    client = ParserClient()
    
    try:
        await client.send_code(phone)
        print("✅ Код отправлен в Telegram!")
        
        code = input("\nВведите код из Telegram: ").strip().replace(' ', '').replace('-', '')
        
        print("\n🔄 Авторизация...")
        await client.sign_in(phone, code)
        
        print("✅ Авторизация успешна!")
        
        # Получаем session string
        session_string = await client.get_session_string()
        me = await client.get_me()
        
        print(f"\n👤 Подключён аккаунт: {me.get('first_name')} (@{me.get('username') or 'без username'})")
        
        # Сохраняем в БД
        db_url = os.getenv('DATABASE_URL')
        if not db_url:
            print("\n❌ DATABASE_URL не найден в .env")
            print(f"\n📋 Session String (сохраните его):")
            print(session_string)
            return
        
        db = DatabasePG(db_url)
        owner_id = int(os.getenv('OWNER_ID', 0))
        
        db.save_parser_session(
            owner_id=owner_id,
            session_string=session_string,
            phone=phone,
            username=me.get('username'),
            user_id=me.get('user_id'),
            first_name=me.get('first_name')
        )
        
        print("\n✅ Парсер-аккаунт успешно сохранён в базу данных!")
        print("\n🚀 Теперь можете запускать парсинг через бота")
        
        await client.disconnect()
        
    except ValueError as e:
        print(f"\n❌ Ошибка: {e}")
    except RuntimeError as e:
        print(f"\n❌ Ошибка: {e}")
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ Отменено пользователем")
