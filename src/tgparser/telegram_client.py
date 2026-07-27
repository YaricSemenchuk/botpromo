"""Telethon userbot: subscribes to configured groups, catches up on missed
messages via per-chat checkpoints after a restart, and feeds every message
through the same `process_message` pipeline (classify -> store -> outbox).

This module needs a live Telegram session to exercise end-to-end (real
phone-number login via scripts/generate_session.py) — that's a manual step
for phase 5 of the rollout (Railway DRY_RUN deploy), not something coverable
by offline unit tests. `process_message` itself has no Telethon dependency
and is covered by tests/test_process_message.py.
"""

from __future__ import annotations

import logging
from typing import Optional

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
) -> None:
    """Idempotent per (chat_id, message_id): classify, log, enqueue for
    sending if caught, and advance the chat's checkpoint. Safe to call
    twice for the same message (catch-up + live event racing) — the second
    call is a no-op once `is_processed` sees the first call's record.
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

    current_checkpoint = store.get_checkpoint(chat_id)
    if current_checkpoint is None or message_id > current_checkpoint:
        store.set_checkpoint(chat_id, message_id)


async def _catch_up(client: TelegramClient, store: Store, group: Group, entity) -> None:
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
        )


async def run(settings: Settings, store: Store) -> None:
    groups = settings.groups
    if not groups:
        logger.warning("groups.yaml is empty — nothing to monitor")
        return

    client = build_client(settings)
    await client.start()

    entities_by_chat_id = {}
    for group in groups:
        entity = await client.get_entity(_resolve_chat_ref(group.chat))
        entities_by_chat_id[tl_utils.get_peer_id(entity)] = (group, entity)
        await _catch_up(client, store, group, entity)

    @client.on(events.NewMessage(chats=[entity for _, entity in entities_by_chat_id.values()]))
    async def _on_new_message(event) -> None:
        group, entity = entities_by_chat_id.get(event.chat_id, (None, None))
        if group is None or not event.message.text:
            return
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
        )

    logger.info("Listening on %s groups", len(entities_by_chat_id))
    await client.run_until_disconnected()
