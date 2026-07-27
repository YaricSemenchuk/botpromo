"""Sends classified leads to the CRM inbound webhook.

Two entry points:
- `send_now`: one-shot send, used for the manual contract test in rollout
  phase 6 (tg:test:1 create -> duplicate check). Raises on failure.
- `OutboxProcessor`: the real traffic path. Drains store.ready_outbox_items(),
  posts each to the CRM, and applies the contract's retry rules — backoff on
  5xx/network errors, no retry (+ alert) on 401/422.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

import httpx

from .config import Settings
from .models import LeadPayload
from .store import OutboxItem, Store

logger = logging.getLogger(__name__)

# Per contract: these mean bad config/data, not a transient failure — never
# retry, alert a human instead of hammering the endpoint.
_NO_RETRY_STATUSES = {401, 422}


class Alerter(Protocol):
    async def notify(self, message: str) -> None: ...


def _backoff_seconds(attempts_so_far: int, settings: Settings) -> float:
    delay = settings.retry_backoff_base_seconds * (2**attempts_so_far)
    return min(delay, settings.retry_backoff_max_seconds)


async def _post_lead(client: httpx.AsyncClient, settings: Settings, payload: dict) -> httpx.Response:
    return await client.post(
        settings.crm_endpoint,
        json=payload,
        headers={"Authorization": f"Bearer {settings.inbound_token}"},
        timeout=settings.http_timeout_seconds,
    )


async def send_now(client: httpx.AsyncClient, settings: Settings, payload: LeadPayload) -> httpx.Response:
    response = await _post_lead(client, settings, payload.to_json())
    response.raise_for_status()
    return response


class OutboxProcessor:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        alerter: Optional[Alerter] = None,
        poll_interval: float = 5.0,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self._settings = settings
        self._store = store
        self._alerter = alerter
        self._poll_interval = poll_interval
        self._client = client or httpx.AsyncClient()
        self._stopped = asyncio.Event()
        # Взводится и при новом лиде, и при остановке: цикл ниже просыпается на
        # любое из двух событий и уже сам разбирается, что произошло.
        self._wake = asyncio.Event()

    async def close(self) -> None:
        await self._client.aclose()

    def stop(self) -> None:
        self._stopped.set()
        self._wake.set()

    def notify(self) -> None:
        """Лид пойман — отправить сейчас, не дожидаясь конца интервала.

        Зовётся из обработчика сообщений Telethon, то есть из того же event
        loop. Если цикл в этот момент занят отправкой, флаг просто останется
        взведённым и следующая итерация начнётся без паузы.
        """
        self._wake.set()

    async def run_forever(self) -> None:
        while not self._stopped.is_set():
            await self.drain_once()
            # Интервал остаётся страховкой: по нему подбираются отложенные
            # ретраи и всё, что могло осесть в очереди мимо notify().
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self._poll_interval)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    async def drain_once(self) -> None:
        for item in self._store.ready_outbox_items():
            await self._process_item(item)

    async def _process_item(self, item: OutboxItem) -> None:
        if self._settings.dry_run:
            logger.info("DRY_RUN: would send lead %s: %s", item.external_id, item.payload)
            self._store.mark_sent(item.external_id, http_status=0)
            self._store.remove_from_outbox(item.external_id)
            return

        try:
            response = await _post_lead(self._client, self._settings, item.payload)
        except httpx.RequestError as exc:
            await self._reschedule(item, str(exc))
            return

        if response.status_code < 300:
            self._store.mark_sent(item.external_id, response.status_code)
            self._store.remove_from_outbox(item.external_id)
            return

        if response.status_code in _NO_RETRY_STATUSES:
            logger.error(
                "CRM rejected lead %s with %s (no retry): %s",
                item.external_id,
                response.status_code,
                response.text,
            )
            self._store.mark_sent(item.external_id, response.status_code)
            self._store.remove_from_outbox(item.external_id)
            if self._alerter:
                await self._alerter.notify(
                    f"tgparser: CRM вернул {response.status_code} на {item.external_id} — "
                    f"конфигурация/данные, не ретраится. {response.text[:300]}"
                )
            return

        # any other non-2xx (5xx etc.) — retry with backoff
        await self._reschedule(item, f"HTTP {response.status_code}: {response.text[:300]}")

    async def _reschedule(self, item: OutboxItem, error: str) -> None:
        attempts_after = item.attempts + 1
        if attempts_after >= self._settings.max_retry_attempts:
            logger.error("Giving up on lead %s after %s attempts: %s", item.external_id, attempts_after, error)
            self._store.remove_from_outbox(item.external_id)
            if self._alerter:
                await self._alerter.notify(
                    f"tgparser: исчерпаны ретраи для {item.external_id} после {attempts_after} попыток: {error}"
                )
            return

        delay = _backoff_seconds(item.attempts, self._settings)
        next_retry_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
        logger.warning("Retrying lead %s in %.0fs (attempt %s): %s", item.external_id, delay, attempts_after, error)
        self._store.reschedule_outbox(item.external_id, next_retry_at, error)
