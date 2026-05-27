import asyncio
import json
import logging
import os
import re
import socket
import tempfile
import time
import urllib.parse

logger = logging.getLogger("SingBoxExecutor")

SINGBOX_BIN = "/usr/local/bin/sing-box"
SINGBOX_STARTUP_TIMEOUT = 4.0
SINGBOX_MAX_PARALLEL = 12

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(SINGBOX_MAX_PARALLEL)
    return _semaphore


def _free_port() -> int:
    for _ in range(30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
                u.bind(("0.0.0.0", port))
            return port
        except OSError:
            continue
    raise OSError("No free port")


def _parse_hy2(link: str) -> dict | None:
    try:
        scheme, rest = link.split("://", 1)
        if "#" in rest:
            rest, _ = rest.rsplit("#", 1)

        if "@" in rest:
            auth_part, hostport = rest.rsplit("@", 1)
        else:
            auth_part = ""
            hostport = rest

        if "?" in hostport:
            hostport, query_str = hostport.split("?", 1)
            params = dict(urllib.parse.parse_qsl(query_str))
        else:
            params = {}

        if hostport.startswith("["):
            bracket_end = hostport.index("]")
            host = hostport[1:bracket_end]
            port_str = hostport[bracket_end + 2:] if bracket_end + 2 < len(hostport) else "443"
        elif ":" in hostport:
            host, port_str = hostport.rsplit(":", 1)
        else:
            return None

        return {
            "server": host.strip(),
            "port": int(port_str),
            "password": urllib.parse.unquote(auth_part) if auth_part else "",
            "sni": params.get("sni", ""),
            "insecure": params.get("insecure", "0") == "1",
            "obfs": params.get("obfs", ""),
            "obfs_password": params.get("obfs-password", ""),
        }
    except Exception:
        return None


def _parse_tuic(link: str) -> dict | None:
    try:
        scheme, rest = link.split("://", 1)
        if "#" in rest:
            rest, _ = rest.rsplit("#", 1)

        if "@" in rest:
            auth_part, hostport = rest.rsplit("@", 1)
        else:
            return None

        if "?" in hostport:
            hostport, query_str = hostport.split("?", 1)
            params = dict(urllib.parse.parse_qsl(query_str))
        else:
            params = {}

        if hostport.startswith("["):
            bracket_end = hostport.index("]")
            host = hostport[1:bracket_end]
            port_str = hostport[bracket_end + 2:] if bracket_end + 2 < len(hostport) else "443"
        elif ":" in hostport:
            host, port_str = hostport.rsplit(":", 1)
        else:
            return None

        if ":" in auth_part:
            uuid_part, password = auth_part.split(":", 1)
        else:
            uuid_part = auth_part
            password = auth_part

        return {
            "_protocol": "tuic",
            "server": host.strip(),
            "port": int(port_str),
            "uuid": urllib.parse.unquote(uuid_part),
            "password": urllib.parse.unquote(password),
            "sni": params.get("sni", ""),
            "alpn": params.get("alpn", "h3"),
            "insecure": params.get("allow_insecure", params.get("insecure", "0")) == "1",
            "congestion_control": params.get("congestion_control", "bbr"),
            "udp_relay_mode": params.get("udp_relay_mode", "native"),
        }
    except Exception:
        return None


def _build_singbox_config(parsed: dict, socks_port: int) -> dict:
    if parsed.get("_protocol") == "tuic":
        outbound: dict = {
            "type": "tuic",
            "tag": "tuic-out",
            "server": parsed["server"],
            "server_port": parsed["port"],
            "uuid": parsed["uuid"],
            "password": parsed["password"],
            "congestion_control": parsed.get("congestion_control", "bbr"),
            "udp_relay_mode": parsed.get("udp_relay_mode", "native"),
            "tls": {
                "enabled": True,
                "server_name": parsed["sni"] or parsed["server"],
                "insecure": parsed["insecure"],
                "alpn": [parsed["alpn"]] if parsed.get("alpn") else ["h3"],
            },
        }
    else:
        outbound = {
            "type": "hysteria2",
            "tag": "hy2-out",
            "server": parsed["server"],
            "server_port": parsed["port"],
            "password": parsed["password"],
            "tls": {
                "enabled": True,
                "server_name": parsed["sni"] or parsed["server"],
                "insecure": parsed["insecure"],
            },
        }
        if parsed.get("obfs"):
            outbound["obfs"] = {
                "type": parsed["obfs"],
                "password": parsed["obfs_password"],
            }

    return {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "socks",
            "tag": "socks-in",
            "listen": "127.0.0.1",
            "listen_port": socks_port,
        }],
        "outbounds": [
            outbound,
            {"type": "direct", "tag": "direct"},
        ],
    }


async def _wait_port_open(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", port), timeout=0.3
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True
        except Exception:
            await asyncio.sleep(0.15)
    return False


async def start_singbox(link: str) -> tuple[asyncio.subprocess.Process | None, int, str | None]:
    scheme = link.split("://", 1)[0].lower() if "://" in link else ""
    if scheme == "tuic":
        parsed = _parse_tuic(link)
        if not parsed:
            return None, 0, "SYS_ERR: Failed to parse tuic link"
    else:
        parsed = _parse_hy2(link)
        if not parsed:
            return None, 0, "SYS_ERR: Failed to parse hy2 link"

    socks_port = _free_port()
    cfg = _build_singbox_config(parsed, socks_port)

    fd, cfg_path = tempfile.mkstemp(prefix="sb_", suffix=".json", dir="/tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(cfg, f)
    except Exception as e:
        try:
            os.unlink(cfg_path)
        except Exception:
            pass
        return None, 0, f"SYS_ERR: Config write failed: {e}"

    try:
        process = await asyncio.create_subprocess_exec(
            SINGBOX_BIN, "run", "-c", cfg_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except Exception as e:
        try:
            os.unlink(cfg_path)
        except Exception:
            pass
        return None, 0, f"SYS_ERR: sing-box launch failed: {e}"

    ready = await _wait_port_open(socks_port, SINGBOX_STARTUP_TIMEOUT)
    if not ready:
        try:
            process.kill()
        except Exception:
            pass
        try:
            os.unlink(cfg_path)
        except Exception:
            pass
        return None, 0, "SYS_ERR: sing-box port not ready"

    return process, socks_port, cfg_path


async def cleanup_singbox(process: asyncio.subprocess.Process | None, cfg_path: str | None):
    if process is not None:
        try:
            process.kill()
        except Exception:
            pass
        try:
            await asyncio.wait_for(process.wait(), timeout=2.0)
        except Exception:
            pass
    if cfg_path and os.path.exists(cfg_path):
        try:
            os.unlink(cfg_path)
        except Exception:
            pass
