import asyncio
import os
import socket
import subprocess
import logging
from pathlib import Path

import aiohttp

_ENV_PATH_FOR_TOKEN = Path(__file__).resolve().parent.parent / ".env"


def _read_token() -> str:
    try:
        for line in _ENV_PATH_FOR_TOKEN.read_text().splitlines():
            if line.startswith("BOT_TOKEN="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return os.getenv("BOT_TOKEN", "")


def _read_owner_id() -> int:
    try:
        for line in _ENV_PATH_FOR_TOKEN.read_text().splitlines():
            if line.startswith("ADMIN_IDS="):
                raw = line.split("=", 1)[1].strip().strip("[]\"' ")
                return int(raw.split(",")[0].strip().strip("\"' "))
    except Exception:
        pass
    try:
        raw = os.getenv("ADMIN_IDS", "0").strip("[]\"' ")
        return int(raw.split(",")[0].strip().strip("\"' "))
    except Exception:
        return 0


BOT_TOKEN = _read_token()
OWNER_ID = _read_owner_id()
CHECK_INTERVAL = 30
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 9998
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ru_proxy_monitor")


def port_alive(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(b"\x05\x01\x00")
            data = sock.recv(2)
            return len(data) == 2 and data[0] == 0x05
    except OSError:
        return False


def read_env_flag() -> bool:
    try:
        with open(ENV_PATH) as f:
            for line in f:
                if line.startswith("CHECKER_USE_RU_PROXY_CHAIN="):
                    return line.strip().split("=", 1)[1].strip().lower() == "true"
    except Exception:
        pass
    return False


def set_env_flag(value: bool) -> None:
    val_str = "True" if value else "False"
    try:
        with open(ENV_PATH) as f:
            content = f.read()
        new_content = "\n".join(
            f"CHECKER_USE_RU_PROXY_CHAIN={val_str}" if line.startswith("CHECKER_USE_RU_PROXY_CHAIN=") else line
            for line in content.splitlines()
        ) + "\n"
        with open(ENV_PATH, "w") as f:
            f.write(new_content)
    except Exception as e:
        log.error(f"Failed to update .env: {e}")


def restart_checker() -> None:
    try:
        subprocess.run(
            ["pm2", "restart", "CheckerSVC", "--update-env"],
            capture_output=True, timeout=30
        )
        log.info("CheckerSVC restarted")
    except Exception as e:
        log.error(f"Failed to restart CheckerSVC: {e}")


async def send_telegram(text: str) -> None:
    if not BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            await s.post(url, json={
                "chat_id": OWNER_ID,
                "text": text,
                "parse_mode": "HTML",
            })
    except Exception as e:
        log.error(f"Telegram send failed: {e}")


async def main() -> None:
    log.info(f"RU proxy monitor started. Checking {PROXY_HOST}:{PROXY_PORT} every {CHECK_INTERVAL}s")

    proxy_was_alive: bool | None = None

    while True:
        alive = port_alive(PROXY_HOST, PROXY_PORT)
        current_flag = read_env_flag()

        if proxy_was_alive is None:
            proxy_was_alive = alive
            if alive:
                log.info("Proxy UP on startup")
            else:
                log.info("Proxy DOWN on startup")
                if current_flag:
                    set_env_flag(False)
                    restart_checker()
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        if alive and not proxy_was_alive:
            log.info("Proxy came back UP")
            proxy_was_alive = True
            if not current_flag:
                set_env_flag(True)
                restart_checker()
            await send_telegram(
                "✅ <b>RU Proxy вернулся!</b>\n\n"
                f"Порт {PROXY_PORT} снова активен — телефон подключён.\n"
                "CHECKER_USE_RU_PROXY_CHAIN переключён в <b>True</b>, CheckerSVC перезапущен."
            )

        elif not alive and proxy_was_alive:
            log.warning("Proxy went DOWN")
            proxy_was_alive = False
            if current_flag:
                set_env_flag(False)
                restart_checker()
            await send_telegram(
                "⚠️ <b>RU Proxy отключился!</b>\n\n"
                f"Порт {PROXY_PORT} недоступен — телефон отвалился или Termux закрылся.\n"
                "CHECKER_USE_RU_PROXY_CHAIN переключён в <b>False</b>, CheckerSVC перезапущен.\n\n"
                "Чтобы снова включить — запусти в Termux:\n"
                "<code>microsocks -p 19090 &amp;\n"
                "ssh -N -R 127.0.0.1:9998:127.0.0.1:19090 root@94.156.179.21</code>"
            )

        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
