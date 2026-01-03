import asyncio
import logging
from database.repo import SubRepo
from utils.vless_checker import VlessChecker

logger = logging.getLogger(__name__)

class BackgroundTasks:
    """
    Класс для фоновых задач бота.
    Запускает проверку подписок по расписанию.
    Использует Queue для стабильной работы с памятью.
    """

    @staticmethod
    async def start_scheduler():
        logger.info("⏳ Background scheduler started.")
        while True:
            try:
                logger.info("🔄 Starting periodic subscription check...")
                await BackgroundTasks.check_all_subscriptions()
                logger.info("✅ Periodic check completed. Waiting 10 minutes.")
            except Exception as e:
                logger.error(f"❌ Error in background task: {e}")

            # Ждем 10 минут (600 секунд) перед следующей проверкой
            await asyncio.sleep(600)

    @staticmethod
    async def check_all_subscriptions():
        subs = await SubRepo.get_all_subscriptions_for_check()
        if not subs:
            return

        queue = asyncio.Queue()
        for sub in subs:
            queue.put_nowait(sub)

        stats = {
            "checked": 0,
            "died": 0,
            "revived": 0,
            "total": len(subs)
        }

        async def worker():
            while True:
                try:
                    sub = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                
                try:
                    parsed = VlessChecker.parse_config(sub.vless_key)
                    is_alive = False
                    latency = 9999

                    if parsed:
                        latency_check = await VlessChecker.check_connection(parsed)
                        if latency_check != -1:
                            is_alive = True
                            latency = latency_check

                    should_update = False

                    if sub.is_active and not is_alive:
                        stats["died"] += 1
                        should_update = True
                    elif not sub.is_active and is_alive:
                        stats["revived"] += 1
                        should_update = True
                    elif is_alive and abs(sub.latency_ms - latency) > 50:
                        should_update = True

                    if should_update or is_alive != sub.is_active:
                         await SubRepo.update_sub_status(sub.id, is_active=is_alive, latency=latency)

                except Exception as e:
                    logger.error(f"Error checking sub {sub.id}: {e}")
                finally:
                    stats["checked"] += 1
                    queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(50)]
        await asyncio.gather(*workers)

        logger.info(
            f"📊 Report: Checked {stats['total']} | "
            f"Revived: {stats['revived']} | Died: {stats['died']}"
        )