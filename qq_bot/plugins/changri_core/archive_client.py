import asyncio

import httpx
from nonebot import logger

from .storage import get_conn


def _get_setting(key: str) -> str | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row is not None else None
    finally:
        conn.close()


def _set_setting(key: str, value: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def is_archive_enabled() -> bool:
    return _get_setting("archive_enabled") == "1"


def set_archive_enabled(enabled: bool) -> None:
    _set_setting("archive_enabled", "1" if enabled else "0")


def get_archive_config() -> tuple[str | None, str | None]:
    return _get_setting("archive_base_url"), _get_setting("archive_token")


def set_archive_config(base_url: str, token: str) -> None:
    _set_setting("archive_base_url", base_url.rstrip("/"))
    _set_setting("archive_token", token)


async def request_archive(method: str, endpoint: str, data: dict | None = None) -> tuple[bool, dict]:
    """需要同步拿到响应结果的调用（如季度创建/结束），不重试，失败直接告诉调用方。"""
    if not is_archive_enabled():
        return False, {"error": "存档功能未启用"}
    base_url, token = get_archive_config()
    if not base_url:
        return False, {"error": "存档服务器未配置"}
    headers = {"Content-Type": "application/json", "X-Archive-Token": token or ""}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.request(method, base_url + endpoint, json=data, headers=headers)
        body = resp.json()
        if resp.status_code >= 300:
            return False, {"error": body.get("error", f"HTTP {resp.status_code}")}
        return True, body
    except httpx.HTTPError as e:
        logger.error(f"[RP存档] {endpoint} 请求失败：{e}")
        return False, {"error": str(e)}


async def post_to_archive(endpoint: str, data: dict) -> None:
    if not is_archive_enabled():
        return
    base_url, token = get_archive_config()
    if not base_url:
        return
    headers = {"Content-Type": "application/json", "X-Archive-Token": token or ""}
    async with httpx.AsyncClient(timeout=10) as client:
        for attempt in range(1, 4):
            try:
                resp = await client.post(base_url + endpoint, json=data, headers=headers)
                if resp.status_code < 300:
                    return
                if resp.status_code < 500:
                    logger.error(f"[RP存档] {endpoint} 返回 {resp.status_code}，不重试")
                    return
                logger.error(f"[RP存档] {endpoint} 返回 {resp.status_code}（第{attempt}次）")
            except httpx.HTTPError as e:
                logger.error(f"[RP存档] 发送失败 {endpoint}（第{attempt}次）：{e}")
            if attempt < 3:
                await asyncio.sleep(attempt * 3)
