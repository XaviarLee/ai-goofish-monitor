"""
飞书自定义机器人通知客户端
"""
import asyncio
from typing import Dict

import requests

from .base import NotificationClient


class FeishuBotClient(NotificationClient):
    """飞书自定义机器人通知客户端"""

    channel_key = "feishu"
    display_name = "飞书"

    def __init__(self, bot_url: str | None = None, pcurl_to_mobile: bool = True):
        super().__init__(enabled=bool(bot_url), pcurl_to_mobile=pcurl_to_mobile)
        self.bot_url = bot_url

    async def send(self, product_data: Dict, reason: str) -> None:
        if not self.is_enabled():
            raise RuntimeError("飞书 未启用")

        message = self._build_message(product_data, reason)
        text_lines = [
            message.notification_title,
            f"价格: {message.price}",
            f"原因: {message.reason}",
        ]
        if message.mobile_link:
            text_lines.append(f"手机端链接: {message.mobile_link}")
        text_lines.append(f"电脑端链接: {message.desktop_link}")

        payload = {
            "msg_type": "text",
            "content": {
                "text": "\n".join(text_lines),
            },
        }
        headers = {"Content-Type": "application/json"}
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.post(
                self.bot_url,
                json=payload,
                headers=headers,
                timeout=10,
            ),
        )
        response.raise_for_status()
        result = response.json()
        status_code = result.get("code", result.get("StatusCode", 0))
        if status_code not in (0, None):
            raise RuntimeError(
                result.get("msg")
                or result.get("StatusMessage")
                or "飞书返回未知错误"
            )
