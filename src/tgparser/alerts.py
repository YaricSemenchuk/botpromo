"""Alerting for config/data errors (401/422) and exhausted retries.

Deliberately a plain Telegram Bot API bot (@BotFather token), not the
userbot/MTProto session used for monitoring — alerting has no business
depending on the listener's login state. Implements the same structural
`notify(message)` protocol that sender.OutboxProcessor expects.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


class NullAlerter:
    """Used when ALERT_BOT_TOKEN/ALERT_CHAT_ID aren't configured — logs only
    so the service still runs without alerting set up."""

    async def notify(self, message: str) -> None:
        logger.warning("ALERT (no alert bot configured): %s", message)


class TelegramBotAlerter:
    def __init__(self, bot_token: str, chat_id: str, client: Optional[httpx.AsyncClient] = None):
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._client = client or httpx.AsyncClient()

    async def close(self) -> None:
        await self._client.aclose()

    async def notify(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        try:
            response = await self._client.post(
                url, json={"chat_id": self._chat_id, "text": message}, timeout=10
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Failed to send alert via Telegram bot: %s (original message: %s)", exc, message)


def build_alerter(settings: Settings):
    if settings.alert_bot_token and settings.alert_chat_id:
        return TelegramBotAlerter(settings.alert_bot_token, settings.alert_chat_id)
    return NullAlerter()
