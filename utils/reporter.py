import logging
from aiogram import Bot
from database.repo import SystemRepo

logger = logging.getLogger("Reporter")

class Reporter:
    CHAT_ID = -1003724265330

    @classmethod
    async def _get_or_create_topic(cls, bot: Bot, topic_name: str, config_key: str) -> int:
        thread_id_str = await SystemRepo.get_config(config_key)
        if thread_id_str:
            return int(thread_id_str)
        
        try:
            topic = await bot.create_forum_topic(chat_id=cls.CHAT_ID, name=topic_name)
            await SystemRepo.set_config(config_key, str(topic.message_thread_id))
            return topic.message_thread_id
        except Exception:
            return 0

    @classmethod
    async def send_new_configs(cls, bot: Bot, count: int, regions: dict):
        thread_id = await cls._get_or_create_topic(bot, "Отчет NewConfigs", "topic_new_configs")
            
        text = f"<b>Кол-во новых конфигов {count}:</b>\n"
        if count > 0:
            for reg, amt in regions.items():
                text += f"{reg} – {amt}\n"
            
        try:
            if thread_id > 0:
                await bot.send_message(chat_id=cls.CHAT_ID, message_thread_id=thread_id, text=text, parse_mode="HTML")
            else:
                await bot.send_message(chat_id=cls.CHAT_ID, text=f"<b>[Отчет NewConfigs]</b>\n{text}", parse_mode="HTML")
        except Exception:
            pass

    @classmethod
    async def send_not_configs(cls, bot: Bot, count: int, reasons: dict):
        thread_id = await cls._get_or_create_topic(bot, "Отчет NotConfigs", "topic_not_configs")
            
        text = f"<b>Кол-во не добавленных конфигов {count}:</b>\n"
        if count > 0:
            text += f"❌ Мертвые (Failed Check): {reasons.get('dead', 0)}\n"
            text += f"🔄 Дубликаты/Blacklist: {reasons.get('dup_or_bl', 0)}\n"
            text += f"⚠️ Ошибки формата: {reasons.get('fmt_err', 0)}\n"
            text += f"⚙️ Системные ошибки чекера: {reasons.get('sys_err', 0)}\n"
            
        try:
            if thread_id > 0:
                await bot.send_message(chat_id=cls.CHAT_ID, message_thread_id=thread_id, text=text, parse_mode="HTML")
            else:
                await bot.send_message(chat_id=cls.CHAT_ID, text=f"<b>[Отчет NotConfigs]</b>\n{text}", parse_mode="HTML")
        except Exception:
            pass

    @classmethod
    async def send_error(cls, bot: Bot, error_msg: str):
        thread_id = await cls._get_or_create_topic(bot, "Errors", "topic_errors")
            
        text = f"⚠️ <b>ОШИБКА:</b>\n<pre>{error_msg}</pre>"
        try:
            if thread_id > 0:
                await bot.send_message(chat_id=cls.CHAT_ID, message_thread_id=thread_id, text=text, parse_mode="HTML")
            else:
                await bot.send_message(chat_id=cls.CHAT_ID, text=f"<b>[Errors]</b>\n{text}", parse_mode="HTML")
        except Exception:
            pass

    @classmethod
    async def send_info(cls, bot: Bot, info_msg: str):
        thread_id = await cls._get_or_create_topic(bot, "Info", "topic_info")
            
        text = f"ℹ️ <b>ИНФО:</b>\n{info_msg}"
        try:
            if thread_id > 0:
                await bot.send_message(chat_id=cls.CHAT_ID, message_thread_id=thread_id, text=text, parse_mode="HTML")
            else:
                await bot.send_message(chat_id=cls.CHAT_ID, text=f"<b>[Info]</b>\n{text}", parse_mode="HTML")
        except Exception:
            pass