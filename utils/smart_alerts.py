import logging
from aiogram import Bot
from config import config
from database.repo import UserRepo, GroupRepo

logger = logging.getLogger("SmartAlerts")

class SmartAlerts:
    @staticmethod
    async def process_changes(old_counts: dict, new_counts: dict):
        bot = Bot(token=config.BOT_TOKEN.get_secret_value())
        try:
            all_regions = set(old_counts.keys()).union(set(new_counts.keys()))
            
            for region in all_regions:
                if "UNK" in region.upper() or "Unk" in region:
                    continue
                    
                old_c = old_counts.get(region, 0)
                new_c = new_counts.get(region, 0)
                
                if old_c > 0 and new_c == 0:
                    await SmartAlerts._notify_region_down(bot, region)
                
                if new_c - old_c >= 20:
                    await SmartAlerts._notify_region_boost(bot, region, new_c - old_c)
        finally:
            await bot.session.close()

    @staticmethod
    async def _notify_region_down(bot: Bot, region: str):
        u_ids = await UserRepo.get_users_with_region(region)
        g_ids = await GroupRepo.get_users_with_group_region(region)
        all_ids = set(u_ids).union(set(g_ids))
        
        text = (
            f"⚠️ <b>Внимание!</b>\n"
            f"Серверы в регионе <b>{region}</b> сейчас недоступны.\n"
            f"Рекомендуем временно выбрать другую страну в настройках профиля."
        )
        
        for uid in all_ids:
            try:
                await bot.send_message(uid, text, parse_mode="HTML")
            except Exception:
                pass

    @staticmethod
    async def _notify_region_boost(bot: Bot, region: str, added: int):
        u_ids = await UserRepo.get_users_with_region(region)
        g_ids = await GroupRepo.get_users_with_group_region(region)
        all_ids = set(u_ids).union(set(g_ids))
        
        text = (
            f"🚀 <b>Отличные новости!</b>\n"
            f"Мы добавили <b>{added}</b> новых серверов в регионе <b>{region}</b>.\n"
            f"Обновите подписку в вашем приложении!"
        )
        
        for uid in all_ids:
            try:
                await bot.send_message(uid, text, parse_mode="HTML")
            except Exception:
                pass