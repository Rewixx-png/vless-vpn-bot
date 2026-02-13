from aiocryptopay import AioCryptoPay, Networks
from config import config

class PaymentClient:
    def __init__(self):
        # Инициализируем клиент CryptoBot
        self.crypto = AioCryptoPay(
            token=config.CRYPTO_BOT_TOKEN.get_secret_value(),
            network=Networks.MAIN_NET
        )

    async def create_invoice(self, amount: float, asset: str = "USDT"):
        """
        Создает инвойс на оплату.
        amount: сумма
        asset: валюта (USDT, TON, BTC)
        """
        try:
            invoice = await self.crypto.create_invoice(
                asset=asset,
                amount=amount,
                description=f"Donation to FreeVPN Bot ({amount} {asset})"
            )
            return invoice
        except Exception as e:
            print(f"Error creating invoice: {e}")
            return None
            
    async def close(self):
        await self.crypto.close()

# Создаем глобальный экземпляр
payment_client = PaymentClient()