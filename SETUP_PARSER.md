# Настройка парсер-аккаунта

## Важно!

Для работы парсинга нужен отдельный Telegram аккаунт (не бот), через который будет происходить поиск NFT в чатах.

## Как подключить парсер-аккаунт:

### Вариант 1: Через отдельный скрипт (рекомендуется)

1. Создайте файл `setup_parser.py`:

```python
import asyncio
import os
from dotenv import load_dotenv
from parsing_telegram_client import ParserClient
from database import DatabasePG

load_dotenv()

async def main():
    phone = input("Введите номер телефона (+79991234567): ")
    
    client = ParserClient()
    await client.send_code(phone)
    
    code = input("Введите код из Telegram: ")
    await client.sign_in(phone, code)
    
    # Получаем session string
    session_string = await client.get_session_string()
    me = await client.get_me()
    
    # Сохраняем в БД
    db = DatabasePG(os.getenv('DATABASE_URL'))
    db.save_parser_session(
        owner_id=int(os.getenv('OWNER_ID')),
        session_string=session_string,
        phone=phone,
        username=me.get('username'),
        user_id=me.get('user_id'),
        first_name=me.get('first_name')
    )
    
    print("✅ Парсер-аккаунт успешно подключён!")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
```

2. Запустите:
```bash
python setup_parser.py
```

### Вариант 2: Автоматически при первом запуске

Бот автоматически попросит подключить парсер-аккаунт при первом запуске, если он ещё не настроен.

## После настройки:

1. Зайдите в админ-панель (`/admin`)
2. Выберите "Управление чатами"
3. Добавьте чаты, в которых будет искать NFT
4. Готово! Теперь пользователи могут запускать парсинг

## Требования к парсер-аккаунту:

- Должен быть добавлен во все чаты, которые вы хотите парсить
- Желательно иметь Premium (для доступа к большему количеству данных)
- Не должен использоваться для других целей (только парсинг)
