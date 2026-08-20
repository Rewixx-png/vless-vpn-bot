import asyncio
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from urllib.parse import unquote, urlparse


from celery_app import app
from config import config, make_bot
from database.repo import SystemRepo
from tasks.base import OptimizedTask, setup_loop_exception_handler_async, logger, setup_log_rotation
from utils.reporter import Reporter


def _parse_postgres_url(db_url: str) -> dict[str, Any]:
    normalized = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlparse(normalized)

    if parsed.scheme not in {"postgresql", "postgres"}:
        raise ValueError("DB_URL must use PostgreSQL")

    db_name = parsed.path.lstrip("/")
    if not db_name:
        raise ValueError("DB_URL must include database name")

    if not parsed.username:
        raise ValueError("DB_URL must include database user")

    return {
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 5432,
        "user": unquote(parsed.username),
        "password": unquote(parsed.password) if parsed.password else "",
        "database": db_name,
    }


@app.task(
    name="tasks.run_backup_snapshot_task",
    base=OptimizedTask,
    time_limit=1800,
    soft_time_limit=1740,
)
async def run_backup_snapshot_task() -> Dict[str, Any]:
    setup_log_rotation()
    await setup_loop_exception_handler_async()

    temp_dir = None
    backup_path = None
    bot = make_bot()

    try:
        await Reporter.send_system_log(bot, "Backup snapshot task started")

        pg = _parse_postgres_url(config.DB_URL)
        utc_now = datetime.now(timezone.utc)
        ts = utc_now.strftime("%Y%m%d_%H%M%S")

        temp_dir = tempfile.mkdtemp(prefix="vless_db_backup_")
        backup_base = f"db_snapshot_{pg['database']}_{ts}"
        dump_name = f"{backup_base}.dump"
        zip_name = f"{backup_base}.zip"
        dump_path = str(Path(temp_dir) / dump_name)
        zip_path = str(Path(temp_dir) / zip_name)

        env = os.environ.copy()
        if pg["password"]:
            env["PGPASSWORD"] = pg["password"]

        cmd = [
            "pg_dump",
            "--format=custom",
            "--compress=9",
            "--no-owner",
            "--no-privileges",
            "--host",
            pg["host"],
            "--port",
            str(pg["port"]),
            "--username",
            pg["user"],
            "--dbname",
            pg["database"],
            "--file",
            dump_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            err_text = stderr.decode("utf-8", errors="ignore")[:1200]
            raise RuntimeError(f"pg_dump failed ({process.returncode}): {err_text}")

        zip_cmd = [
            "zip",
            "-j",
            "-q",
            "-P",
            config.BACKUP_ZIP_PASSWORD,
            zip_path,
            dump_path,
        ]
        zip_process = await asyncio.create_subprocess_exec(
            *zip_cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, zip_stderr = await zip_process.communicate()

        if zip_process.returncode != 0:
            err_text = zip_stderr.decode("utf-8", errors="ignore")[:1200]
            raise RuntimeError(
                f"zip encryption failed ({zip_process.returncode}): {err_text}"
            )

        size_bytes = os.path.getsize(zip_path)
        size_mb = size_bytes / (1024 * 1024)
        caption = (
            "🗄 <b>DB BackUp Snapshot</b>\n"
            f"БД: <code>{pg['database']}</code>\n"
            f"Размер: <b>{size_mb:.2f} MB</b>\n"
            f"UTC: <code>{utc_now.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            "Формат: <code>ZIP (пароль)</code>\n"
            "Внутри: <code>pg_dump -Fc</code>"
        )

        sent = await Reporter.send_backup_document(
            bot=bot,
            file_path=zip_path,
            file_name=zip_name,
            caption=caption,
        )
        if not sent:
            raise RuntimeError("failed to send backup snapshot to report chat")

        await SystemRepo.set_config("backup_last_snapshot_utc", utc_now.isoformat())
        await SystemRepo.set_config("backup_last_snapshot_size_mb", f"{size_mb:.2f}")

        await Reporter.send_system_log(
            bot,
            f"Backup snapshot completed: file={zip_name}, size={size_mb:.2f}MB",
        )

        return {
            "status": "ok",
            "file": zip_name,
            "size_mb": round(size_mb, 2),
        }
    except Exception as e:
        logger.error(f"Backup snapshot failed: {e}")
        try:
            await Reporter.send_error(bot, f"Backup snapshot failed: {e}")
            await Reporter.send_system_log(bot, f"Backup snapshot failed: {e}")
        except Exception:
            pass
        raise
    finally:
        try:
            await bot.session.close()
        except Exception:
            pass

        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
