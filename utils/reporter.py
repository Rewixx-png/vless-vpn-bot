import html
import logging
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile

from config import config
from database.repo import SystemRepo

logger = logging.getLogger("Reporter")


class Reporter:
    MAX_MESSAGE_LEN = 3800

    @staticmethod
    def _trim(text: str, max_len: int = MAX_MESSAGE_LEN) -> str:
        if len(text) <= max_len:
            return text
        return text[: max_len - 26] + "\n<i>... сообщение обрезано</i>"

    @staticmethod
    def _escape(value: object) -> str:
        return html.escape(str(value), quote=False)

    @classmethod
    async def _create_topic(
        cls,
        bot: Bot,
        topic_name: str,
        config_key: str,
    ) -> int:
        if not config.REPORT_CHAT_ID:
            return 0
            
        try:
            topic = await bot.create_forum_topic(
                chat_id=config.REPORT_CHAT_ID,
                name=topic_name,
            )
            thread_id = int(topic.message_thread_id)
            await SystemRepo.set_config(config_key, str(thread_id))
            return thread_id
        except Exception as error:
            logger.warning(
                "Failed to create forum topic '%s': %s",
                topic_name,
                error,
            )
            return 0

    @classmethod
    async def _get_or_create_topic(
        cls,
        bot: Bot,
        topic_name: str,
        config_key: str,
    ) -> int:
        thread_id_raw = await SystemRepo.get_config(config_key)
        if thread_id_raw:
            try:
                return int(thread_id_raw)
            except ValueError:
                await SystemRepo.delete_config(config_key)

        return await cls._create_topic(
            bot=bot,
            topic_name=topic_name,
            config_key=config_key,
        )

    @classmethod
    async def _send_text(
        cls,
        bot: Bot,
        topic_name: str,
        config_key: str,
        text: str,
        fallback_prefix: str,
    ) -> None:
        if not config.REPORT_CHAT_ID:
            logger.info(f"Report '{topic_name}' skipped (REPORT_CHAT_ID is not set)")
            return
            
        payload = cls._trim(text)
        thread_id = await cls._get_or_create_topic(
            bot=bot,
            topic_name=topic_name,
            config_key=config_key,
        )

        if thread_id > 0:
            try:
                await bot.send_message(
                    chat_id=config.REPORT_CHAT_ID,
                    message_thread_id=thread_id,
                    text=payload,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                return
            except TelegramBadRequest as error:
                err_text = str(error).lower()
                if "thread" in err_text or "message thread not found" in err_text:
                    await SystemRepo.delete_config(config_key)
                    new_thread_id = await cls._create_topic(
                        bot=bot,
                        topic_name=topic_name,
                        config_key=config_key,
                    )
                    if new_thread_id > 0:
                        try:
                            await bot.send_message(
                                chat_id=config.REPORT_CHAT_ID,
                                message_thread_id=new_thread_id,
                                text=payload,
                                parse_mode="HTML",
                                disable_web_page_preview=True,
                            )
                            return
                        except Exception as retry_error:
                            logger.error(
                                "Retry send to topic '%s' failed: %s",
                                topic_name,
                                retry_error,
                            )
                else:
                    logger.error(
                        "Send to topic '%s' failed: %s",
                        topic_name,
                        error,
                    )
            except Exception as error:
                logger.error("Send to topic '%s' failed: %s", topic_name, error)

        try:
            await bot.send_message(
                chat_id=config.REPORT_CHAT_ID,
                text=f"<b>[{cls._escape(fallback_prefix)}]</b>\n{payload}",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as error:
            logger.error("Fallback send failed for '%s': %s", fallback_prefix, error)

    @classmethod
    async def send_new_configs(
        cls,
        bot: Bot,
        count: int,
        regions: dict,
        meta: Optional[dict] = None,
    ) -> None:
        lines = [f"🆕 <b>Новые конфиги:</b> {count}"]

        if meta:
            processed = int(meta.get("processed", 0) or 0)
            rejected = int(meta.get("rejected", 0) or 0)
            sources_used = int(meta.get("sources_used", 0) or 0)
            custom_sources = int(meta.get("custom_sources_used", 0) or 0)
            duration = float(meta.get("duration", 0.0) or 0.0)
            lines.append(
                "📊 <b>Статистика:</b> "
                f"processed={processed}, rejected={rejected}, "
                f"sources={sources_used} (custom={custom_sources}), "
                f"duration={duration:.1f}s"
            )

        if count > 0 and regions:
            lines.append("\n🌍 <b>По регионам:</b>")
            sorted_regions = sorted(
                regions.items(),
                key=lambda item: item[1],
                reverse=True,
            )
            visible = sorted_regions[:40]
            for region, amount in visible:
                lines.append(f"• {cls._escape(region)}: <b>+{int(amount)}</b>")
            hidden = len(sorted_regions) - len(visible)
            if hidden > 0:
                lines.append(f"• ... и еще {hidden} регионов")
        else:
            lines.append("\nℹ️ Новых конфигов в этом запуске нет.")

        await cls._send_text(
            bot=bot,
            topic_name="Отчет NewConfigs",
            config_key="topic_new_configs",
            text="\n".join(lines),
            fallback_prefix="Отчет NewConfigs",
        )

    @classmethod
    async def send_not_configs(
        cls,
        bot: Bot,
        count: int,
        reasons: dict,
        meta: Optional[dict] = None,
    ) -> None:
        dead = int(reasons.get("dead", 0) or 0)
        dup_or_bl = int(reasons.get("dup_or_bl", 0) or 0)
        fmt_err = int(reasons.get("fmt_err", 0) or 0)
        sys_err = int(reasons.get("sys_err", 0) or 0)

        lines = [
            f"🚫 <b>Не добавлено конфигов:</b> {count}",
            "📉 <b>Причины:</b>",
            f"• Dead/Failed Check: <b>{dead}</b>",
            f"• Duplicate/Blacklist: <b>{dup_or_bl}</b>",
            f"• Format Error: <b>{fmt_err}</b>",
            f"• System Error: <b>{sys_err}</b>",
        ]

        if meta:
            processed = int(meta.get("processed", 0) or 0)
            lines.append(f"\n📊 Processed: <b>{processed}</b>")

        await cls._send_text(
            bot=bot,
            topic_name="Отчет NotConfigs",
            config_key="topic_not_configs",
            text="\n".join(lines),
            fallback_prefix="Отчет NotConfigs",
        )

    @classmethod
    async def send_error(cls, bot: Bot, error_msg: str) -> None:
        safe = cls._escape(error_msg)
        text = f"⚠️ <b>ОШИБКА</b>\n<pre>{safe}</pre>"
        await cls._send_text(
            bot=bot,
            topic_name="Errors",
            config_key="topic_errors",
            text=text,
            fallback_prefix="Errors",
        )

    @classmethod
    async def send_info(cls, bot: Bot, info_msg: str) -> None:
        text = f"ℹ️ <b>INFO</b>\n{cls._trim(info_msg)}"
        await cls._send_text(
            bot=bot,
            topic_name="INFO",
            config_key="topic_info",
            text=text,
            fallback_prefix="Info",
        )

    @classmethod
    async def send_collector_log(cls, bot: Bot, message: str) -> None:
        await cls._send_text(
            bot=bot,
            topic_name="Collector Logs",
            config_key="topic_collector",
            text=f"🧲 <b>Collector</b>\n{cls._trim(message)}",
            fallback_prefix="Collector",
        )

    @classmethod
    async def send_stability_log(cls, bot: Bot, message: str) -> None:
        await cls._send_text(
            bot=bot,
            topic_name="Stability Logs",
            config_key="topic_stability",
            text=f"🛡 <b>Stability</b>\n{cls._trim(message)}",
            fallback_prefix="Stability",
        )

    @classmethod
    async def send_system_log(cls, bot: Bot, message: str) -> None:
        await cls._send_text(
            bot=bot,
            topic_name="System Events",
            config_key="topic_system",
            text=f"🧭 <b>System</b>\n{cls._trim(message)}",
            fallback_prefix="System",
        )

    @classmethod
    async def send_user_action(cls, bot: Bot, message: str) -> None:
        await cls._send_text(
            bot=bot,
            topic_name="User Actions",
            config_key="topic_user_actions",
            text=f"👤 <b>User Action</b>\n{cls._trim(message)}",
            fallback_prefix="User Action",
        )

    @classmethod
    async def send_admin_action(cls, bot: Bot, message: str) -> None:
        await cls._send_text(
            bot=bot,
            topic_name="Admin Actions",
            config_key="topic_admin_actions",
            text=f"🔐 <b>Admin Action</b>\n{cls._trim(message)}",
            fallback_prefix="Admin Action",
        )

    @classmethod
    async def send_backup_document(
        cls,
        bot: Bot,
        file_path: str,
        file_name: str,
        caption: str,
    ) -> bool:
        if not config.REPORT_CHAT_ID:
            return False
            
        thread_id = await cls._get_or_create_topic(bot, "BackUp", "topic_backup")
        document = FSInputFile(file_path, filename=file_name)

        try:
            if thread_id > 0:
                await bot.send_document(
                    chat_id=config.REPORT_CHAT_ID,
                    message_thread_id=thread_id,
                    document=document,
                    caption=cls._trim(caption),
                    parse_mode="HTML",
                )
            else:
                await bot.send_document(
                    chat_id=config.REPORT_CHAT_ID,
                    document=document,
                    caption=cls._trim(f"<b>[BackUp]</b>\n{caption}"),
                    parse_mode="HTML",
                )
            return True
        except Exception as error:
            logger.error("Failed to send backup document: %s", error)
            return False
