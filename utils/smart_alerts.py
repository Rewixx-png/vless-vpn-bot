import logging
import asyncio
from datetime import datetime, time
from aiogram import Bot
from config import config
from database.repo import UserRepo

logger = logging.getLogger("SmartAlerts")

class SmartAlerts:
    _accumulated_adds = {}
    _accumulated_drops = set()
    _lock = asyncio.Lock()
    
    @classmethod
    async def process_changes(cls, old_counts: dict, new_counts: dict):
        all_regions = set(old_counts.keys()).union(set(new_counts.keys()))
        
        async with cls._lock:
            for region in all_regions:
                if "UNK" in region.upper() or "Unk" in region:
                    continue
                    
                old_c = old_counts.get(region, 0)
                new_c = new_counts.get(region, 0)
                
                if old_c > 0 and new_c == 0:
                    cls._accumulated_drops.add(region)
                    logger.info(f"📉 Region {region} marked as down (accumulated)")
                
                added = new_c - old_c
                if added >= 20:
                    if region in cls._accumulated_adds:
                        cls._accumulated_adds[region] += added
                    else:
                        cls._accumulated_adds[region] = added
                    logger.info(f"📈 Added {added} servers in {region} (accumulated, total: {cls._accumulated_adds[region]})")
    
    @classmethod
    async def send_daily_digest(cls, bot: Bot = None):
        async with cls._lock:
            if not cls._accumulated_adds and not cls._accumulated_drops:
                logger.info("📭 No notifications to send in daily digest")
                return
            
            all_users = await UserRepo.get_all_users()
            all_ids = set(all_users)
            
            if not all_ids:
                logger.warning("⚠️ No users to notify")
                return
            
            messages = []
            
            messages.append("🚀 <b>Ежедневная сводка по серверам</b>\n")
            messages.append(f"📅 <i>{datetime.now().strftime('%d.%m.%Y')}</i>\n")
            messages.append("━" * 20 + "\n\n")
            
            if cls._accumulated_adds:
                total_added = sum(cls._accumulated_adds.values())
                messages.append(f"📈 <b>Добавлено серверов:</b> {total_added}\n\n")
                
                sorted_regions = sorted(cls._accumulated_adds.items(), key=lambda x: x[1], reverse=True)
                for region, count in sorted_regions:
                    messages.append(f"  • {region}: +{count} серверов\n")
                messages.append("\n")
            
            if cls._accumulated_drops:
                messages.append(f"⚠️ <b>Стали недоступны регионы:</b> {len(cls._accumulated_drops)}\n\n")
                for region in sorted(cls._accumulated_drops):
                    messages.append(f"  • {region}\n")
                messages.append("\n")
            
            messages.append("━" * 20 + "\n")
            messages.append("💡 <i>Обновите подписку в вашем приложении для получения новых серверов</i>")
            
            full_message = "".join(messages)
            
            max_length = 3500
            message_parts = []
            current_part = ""
            
            for line in messages:
                if len(current_part) + len(line) > max_length:
                    message_parts.append(current_part)
                    current_part = line
                else:
                    current_part += line
            
            if current_part:
                message_parts.append(current_part)
            
            if bot is None:
                bot = Bot(token=config.BOT_TOKEN.get_secret_value())
                close_bot = True
            else:
                close_bot = False
            
            try:
                sent_count = 0
                failed_count = 0
                
                for user_id in all_ids:
                    try:
                        for part in message_parts:
                            await bot.send_message(user_id, part, parse_mode="HTML")
                            await asyncio.sleep(0.1)
                        sent_count += 1
                    except Exception as e:
                        logger.debug(f"Failed to send digest to {user_id}: {e}")
                        failed_count += 1
                
                logger.info(f"📬 Daily digest sent: {sent_count} users, {failed_count} failed")
                
            finally:
                if close_bot:
                    await bot.session.close()
            
            cls._accumulated_adds.clear()
            cls._accumulated_drops.clear()
    
    @staticmethod
    async def _notify_region_down(bot: Bot, region: str):
        pass
    
    @staticmethod
    async def _notify_region_boost(bot: Bot, region: str, added: int):
        pass
