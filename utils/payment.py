import logging

try:
    from aiocryptopay import AioCryptoPay, Networks
except Exception:
    AioCryptoPay = None
    Networks = None

from config import config

logger = logging.getLogger("Payment")


class PaymentClient:
    def __init__(self):
        self._crypto = None

    @staticmethod
    def _token_value() -> str:
        if not config.CRYPTO_BOT_TOKEN:
            return ""
        return config.CRYPTO_BOT_TOKEN.get_secret_value().strip()

    @classmethod
    def _is_enabled(cls) -> bool:
        return bool(AioCryptoPay and Networks and cls._token_value())

    async def get_client(self):
        if not self._is_enabled():
            return None

        if self._crypto is None:
            self._crypto = AioCryptoPay(
                token=self._token_value(),
                network=Networks.MAIN_NET
            )
        return self._crypto

    async def create_invoice(self, amount: float, asset: str = "USDT"):
        try:
            client = await self.get_client()
            if client is None:
                logger.warning(
                    "CryptoPay disabled: install aiocryptopay and set CRYPTO_BOT_TOKEN"
                )
                return None

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
