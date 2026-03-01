import logging
from aiocryptopay import AioCryptoPay, Networks
from config import config

logger = logging.getLogger("Payment")

class PaymentClient:
    def __init__(self):
        self._crypto = None

    async def get_client(self):
        if self._crypto is None:
            self._crypto = AioCryptoPay(
                token=config.CRYPTO_BOT_TOKEN.get_secret_value(),
                network=Networks.MAIN_NET
            )
        return self._crypto

    async def create_invoice(self, amount: float, asset: str = "USDT"):
        try:
            client = await self.get_client()
            invoice = await client.create_invoice(
                asset=asset,
                amount=amount,
                description=f"Donation to VPN Bot ({amount} {asset})"
            )
            return invoice
        except Exception as e:
            logger.error(f"Error creating invoice: {e}")
            return None
            
    async def close(self):
        if self._crypto:
            await self._crypto.close()
            self._crypto = None

payment_client = PaymentClient()