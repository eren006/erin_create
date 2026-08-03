"""NoneBot 校园校报文字版。网页与机器人共用 newspaper_service。"""

from __future__ import annotations

from newspaper_service import build_text, publish_text


def build(end_day: int | None = None) -> str:
    return build_text(end_day)


def publish(end_day: int) -> str:
    return publish_text(end_day)
