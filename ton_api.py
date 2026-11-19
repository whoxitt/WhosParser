"""
TON Console API для проверки платежей
"""
import requests
import logging
from typing import Optional

log = logging.getLogger('ton_api')


class TonConsoleAPI:
    """Класс для работы с TON Console API"""
    
    def __init__(self, api_key: str, wallet_address: str):
        """
        Args:
            api_key: API ключ от TON Console
            wallet_address: Адрес кошелька для приёма платежей
        """
        self.api_key = api_key
        self.wallet_address = wallet_address
        self.base_url = "https://tonconsole.com/api/v1"
    
    def check_payment(self, memo: str, amount: float = 5.0) -> Optional[dict]:
        """
        Проверить был ли платёж с указанным MEMO
        
        Args:
            memo: Уникальный комментарий платежа
            amount: Ожидаемая сумма в TON
            
        Returns:
            dict с информацией о транзакции или None если не найдена
        """
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            # Получаем последние транзакции кошелька
            response = requests.get(
                f'{self.base_url}/transactions',
                headers=headers,
                params={
                    'address': self.wallet_address,
                    'limit': 100
                },
                timeout=10
            )
            
            if response.status_code != 200:
                log.error('Ошибка TON API: %s', response.text)
                return None
            
            data = response.json()
            transactions = data.get('transactions', [])
            
            # Ищем транзакцию с нужным MEMO и суммой
            for tx in transactions:
                tx_memo = tx.get('comment', '').strip()
                tx_amount = float(tx.get('amount', 0)) / 1e9  # Конвертируем из nanotons
                
                if tx_memo == memo and tx_amount >= amount:
                    return {
                        'tx_hash': tx.get('hash'),
                        'amount': tx_amount,
                        'memo': tx_memo,
                        'timestamp': tx.get('timestamp')
                    }
            
            return None
            
        except Exception as e:
            log.exception('Ошибка проверки платежа: %s', e)
            return None
