"""One-off interactive login for the userbot account.

Run locally (not on Railway — needs an interactive terminal for the SMS/2FA
code): asks for TG_API_ID/TG_API_HASH (or reads them from env/.env if
already set), logs in with the phone number, and prints a StringSession to
paste into Railway as TG_SESSION_STRING. The session string is a credential
equivalent to full account access — treat it like a password, never commit
it or paste it anywhere but the Railway env var.

Usage:
    python scripts/generate_session.py
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()


async def main() -> None:
    api_id = int(os.environ.get("TG_API_ID") or input("TG_API_ID: ").strip())
    api_hash = os.environ.get("TG_API_HASH") or input("TG_API_HASH: ").strip()

    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        session_string = client.session.save()
        print("\n=== TG_SESSION_STRING (сохрани как секрет в Railway, не в код) ===\n")
        print(session_string)
        print()


if __name__ == "__main__":
    asyncio.run(main())
