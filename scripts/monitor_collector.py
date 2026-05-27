import asyncio
import time
import subprocess
import requests
import os
import sys
import json

sys.path.append("/root/Projects/vless-vpn-bot")
from database.core import engine
from sqlalchemy import text
from config import config

BOT_TOKEN = config.BOT_TOKEN.get_secret_value()
CHAT_ID = "7485721661"

def is_collector_running():
    try:
        env = os.environ.copy()
        out = subprocess.check_output(
            ["/root/Projects/vless-vpn-bot/.venv/bin/celery", "-A", "celery_app", "inspect", "active"], 
            timeout=15, 
            text=True,
            env=env,
            cwd="/root/Projects/vless-vpn-bot"
        )
        return "tasks.run_collector_task" in out
    except Exception as e:
        return True # Keep waiting if command fails temporarily

async def main():
    # Wait until collector finishes
    while is_collector_running():
        await asyncio.sleep(30)
    
    # Finished, wait a bit for DB commit
    await asyncio.sleep(5)
    
    # Check stats
    stats = "{}"
    async with engine.begin() as conn:
        res = await conn.execute(text("SELECT value FROM system_config WHERE key = 'collector_last_run'"))
        row = res.fetchone()
        if row:
            stats = row[0]
            
    try:
        data = json.loads(stats)
        added = data.get("added", 0)
        processed = data.get("processed", 0)
        
        if added > 0:
            msg = f"🟢 Коллектор закончил работу!\n\n✅ Добавлено конфигов: {added}\n🔍 Всего проверено: {processed}\n\nВсё работает отлично, приятного отдыха в ТТ! 😎"
        else:
            msg = f"🔴 Коллектор закончил работу, но...\n\n❌ Добавлено конфигов: 0\n🔍 Было проверено: {processed}\n\nЯ не могу писать сам в окно с кодом, пока вы мне не ответите. Возвращайтесь из ТТ и напишите мне в чат ОпенКода, будем искать причину, почему всё отбраковалось!"
    except Exception as e:
        msg = f"Коллектор закончил работу. Статус не удалось прочитать. Ошибка: {e}"

    # Send message via TG API
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg})

if __name__ == "__main__":
    asyncio.run(main())
