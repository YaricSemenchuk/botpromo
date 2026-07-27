"""Telethon userbot: subscribes to the configured groups and feeds every new
message through the `process_message` pipeline (classify -> store -> outbox).

Live subscription, not a poll loop: a lead reaches the CRM seconds after it is
posted, which is the whole point of watching chats where requests are answered
within the hour. Per-chat checkpoints turn every start into a catch-up, so a
restart or a lost connection doesn't drop the gap.

This module needs a live Telegram session to exercise end-to-end (real
phone-number login via scripts/generate_session.py) — that's a manual step
for phase 5 of the rollout (Railway DRY_RUN deploy), not something coverable
by offline unit tests. `process_message` itself has no Telethon dependency
and is covered by tests/test_process_message.py.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from telethon import TelegramClient, events
from telethon import utils as tl_utils
from telethon.sessions import StringSession

from .classifier import classify
from .config import Group, Settings
from .models import LeadPayload
from .store import Store

logger = logging.getLogger(__name__)


def _resolve_chat_ref(chat: str):
    stripped = chat.lstrip("-")
    return int(chat) if stripped.isdigit() else chat


def _message_link(chat_id: int, message_id: int, chat_username: Optional[str]) -> str:
    if chat_username:
        return f"https://t.me/{chat_username}/{message_id}"
    real_id, _ = tl_utils.resolve_id(chat_id)
    return f"https://t.me/c/{real_id}/{message_id}"


def _sender_display(sender) -> tuple[str, Optional[str]]:
    username = getattr(sender, "username", None)
    first = getattr(sender, "first_name", None) or ""
    last = getattr(sender, "last_name", None) or ""
    full_name = f"{first} {last}".strip()
    name = full_name or (f"@{username}" if username else "Без имени")
    return name, username


def build_client(settings: Settings) -> TelegramClient:
    return TelegramClient(
        StringSession(settings.tg_session_string),
        settings.tg_api_id,
        settings.tg_api_hash,
    )


def process_message(
    store: Store,
    *,
    chat_id: int,
    message_id: int,
    chat_name: str,
    text: str,
    sender_name: str,
    sender_username: Optional[str],
    link: str,
    on_lead: Optional[Callable[[], None]] = None,
) -> None:
    """Idempotent per (chat_id, message_id): classify, log, enqueue for
    sending if caught, and advance the chat's checkpoint. Safe to call
    twice for the same message (catch-up + live event racing) — the second
    call is a no-op once `is_processed` sees the first call's record.

    `on_lead` fires right after a caught lead lands in the outbox — that's
    how OutboxProcessor learns to send it now instead of on its next poll.
    """
    external_id = f"tg:{chat_id}:{message_id}"
    if store.is_processed(external_id):
        return

    result = classify(text or "")
    store.record_processed(external_id, chat_id, message_id, result.action, result.tag)

    if result.action == "catch":
        meta = {"group": chat_name}
        if result.tag:
            meta["tag"] = result.tag
        payload = LeadPayload(
            source="tg",
            external_id=external_id,
            name=sender_name,
            text=text,
            telegram=f"@{sender_username}" if sender_username else None,
            link=link,
            meta=meta,
        )
        store.enqueue_outbox(external_id, payload.to_json())
        if on_lead is not None:
            on_lead()

    current_checkpoint = store.get_checkpoint(chat_id)
    if current_checkpoint is None or message_id > current_checkpoint:
        store.set_checkpoint(chat_id, message_id)


async def _catch_up(
    client: TelegramClient, store: Store, group: Group, entity, on_lead: Optional[Callable[[], None]] = None
) -> None:
    chat_id = tl_utils.get_peer_id(entity)
    checkpoint = store.get_checkpoint(chat_id)

    if checkpoint is None:
        # First time we see this chat: don't mine full history, just mark
        # "caught up as of now" so a later restart can catch up from here.
        latest = await client.get_messages(entity, limit=1)
        if latest:
            store.set_checkpoint(chat_id, latest[0].id)
        return

    async for message in client.iter_messages(entity, min_id=checkpoint, reverse=True):
        if not message.text:
            continue
        sender = await message.get_sender()
        name, username = _sender_display(sender) if sender else ("Без имени", None)
        link = _message_link(chat_id, message.id, getattr(entity, "username", None))
        process_message(
            store,
            chat_id=chat_id,
            message_id=message.id,
            chat_name=group.name,
            text=message.text,
            sender_name=name,
            sender_username=username,
            link=link,
            on_lead=on_lead,
        )


# Как часто перепроверять группы, которые пока не открылись.
_PENDING_RETRY_SECONDS = 600


async def _resolve_groups(client, store: Store, pending: list[Group], resolved: dict, on_lead) -> list[Group]:
    """Opens the groups we don't have an entity for yet and catches each newly
    opened one up; returns the ones still unavailable.

    A group can be unopenable for a while — join request awaiting approval,
    renamed username, kicked out — and that must not take the others down.
    """
    still_pending = []
    for group in pending:
        try:
            entity = await client.get_entity(_resolve_chat_ref(group.chat))
        except Exception as exc:
            still_pending.append(group)
            logger.warning("Group %s (%s) unavailable: %s", group.chat, group.name, exc)
            continue
        resolved[tl_utils.get_peer_id(entity)] = (group, entity)
        logger.info("Opened %s (%s)", group.chat, group.name)
        # Catch-up is best-effort: history can be closed for a member while new
        # messages still arrive. Failing it must not drop the group.
        try:
            await _catch_up(client, store, group, entity, on_lead=on_lead)
        except Exception as exc:
            logger.warning("Catch-up failed for %s: %s — listening for new messages anyway", group.chat, exc)
    return still_pending


async def _retry_pending(client, store: Store, pending: list[Group], resolved: dict, on_lead) -> None:
    """Re-opens groups that weren't available at startup, so an approval that
    lands an hour after deploy joins the rotation without a restart."""
    while pending:
        await asyncio.sleep(_PENDING_RETRY_SECONDS)
        pending = await _resolve_groups(client, store, pending, resolved, on_lead)


async def run(settings: Settings, store: Store, on_lead: Optional[Callable[[], None]] = None) -> None:
    """Subscribes to every available group and processes messages as they arrive."""
    groups = settings.groups
    if not groups:
        logger.warning("groups.yaml is empty — nothing to monitor")
        return

    client = build_client(settings)
    await client.start()

    resolved: dict[int, tuple[Group, object]] = {}
    pending = await _resolve_groups(client, store, list(groups), resolved, on_lead)
    if pending:
        logger.warning(
            "%s of %s groups unavailable: %s — will retry every %g min",
            len(pending), len(groups), ", ".join(g.chat for g in pending), _PENDING_RETRY_SECONDS / 60,
        )
    if not resolved and not pending:
        logger.error("No group could be opened — check that the account joined them and requests were approved")

    # Подписка без фильтра по чатам, а отбор по chat_id внутри: список групп
    # пополняется на ходу (см. _retry_pending), а у зарегистрированного
    # обработчика фильтр chats=[...] уже не поменять.
    @client.on(events.NewMessage())
    async def _on_new_message(event) -> None:
        entry = resolved.get(event.chat_id)
        if entry is None or not event.message.text:
            return
        group, entity = entry
        sender = await event.get_sender()
        name, username = _sender_display(sender) if sender else ("Без имени", None)
        link = _message_link(event.chat_id, event.message.id, getattr(entity, "username", None))
        process_message(
            store,
            chat_id=event.chat_id,
            message_id=event.message.id,
            chat_name=group.name,
            text=event.message.text,
            sender_name=name,
            sender_username=username,
            link=link,
            on_lead=on_lead,
        )

    retry_task = asyncio.create_task(_retry_pending(client, store, pending, resolved, on_lead))
    logger.info("Listening on %s groups", len(resolved))
    try:
        await client.run_until_disconnected()
    finally:
        retry_task.cancel()

        await asyncio.sleep(interval)
