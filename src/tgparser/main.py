from __future__ import annotations

import asyncio
import logging

from . import telegram_client
from .alerts import build_alerter
from .config import load_settings
from .sender import OutboxProcessor
from .store import Store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = load_settings()
    logger.info("Starting tgparser (DRY_RUN=%s, groups=%s)", settings.dry_run, len(settings.groups))

    store = Store(settings.db_path)
    alerter = build_alerter(settings)
    outbox = OutboxProcessor(settings, store, alerter=alerter)

    try:
        await asyncio.gather(
            outbox.run_forever(),
            telegram_client.run(settings, store),
        )
    finally:
        await outbox.close()
        store.close()


if __name__ == "__main__":
    asyncio.run(main())
