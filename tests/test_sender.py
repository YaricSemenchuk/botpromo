import httpx
import pytest

from tgparser.sender import OutboxProcessor
from tgparser.store import Store

from .conftest import make_settings


class FakeAlerter:
    def __init__(self):
        self.messages = []

    async def notify(self, message: str) -> None:
        self.messages.append(message)


def _client_with_handler(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_dry_run_marks_sent_without_http_call(tmp_path):
    settings = make_settings(tmp_path, dry_run=True)
    store = Store(settings.db_path)
    store.enqueue_outbox("tg:1:1", {"externalId": "tg:1:1"})

    async def handler(request):
        raise AssertionError("dry run must not perform HTTP calls")

    processor = OutboxProcessor(settings, store, client=_client_with_handler(handler))
    await processor.drain_once()
    await processor.close()

    assert store.ready_outbox_items() == []


async def test_success_response_removes_from_outbox(tmp_path):
    settings = make_settings(tmp_path)
    store = Store(settings.db_path)
    store.enqueue_outbox("tg:1:1", {"externalId": "tg:1:1"})

    async def handler(request):
        assert request.headers["authorization"] == "Bearer test-token"
        return httpx.Response(200, json={"ok": True, "created": True})

    processor = OutboxProcessor(settings, store, client=_client_with_handler(handler))
    await processor.drain_once()
    await processor.close()

    assert store.ready_outbox_items() == []


async def test_401_is_not_retried_and_alerts(tmp_path):
    settings = make_settings(tmp_path)
    store = Store(settings.db_path)
    store.enqueue_outbox("tg:1:1", {"externalId": "tg:1:1"})
    alerter = FakeAlerter()

    async def handler(request):
        return httpx.Response(401, json={"error": "unauthorized"})

    processor = OutboxProcessor(settings, store, alerter=alerter, client=_client_with_handler(handler))
    await processor.drain_once()
    await processor.close()

    assert store.ready_outbox_items() == []
    assert len(alerter.messages) == 1
    assert "401" in alerter.messages[0]


async def test_422_is_not_retried_and_alerts(tmp_path):
    settings = make_settings(tmp_path)
    store = Store(settings.db_path)
    store.enqueue_outbox("tg:1:1", {"externalId": "tg:1:1"})
    alerter = FakeAlerter()

    async def handler(request):
        return httpx.Response(422, json={"error": "missing field", "field": "text"})

    processor = OutboxProcessor(settings, store, alerter=alerter, client=_client_with_handler(handler))
    await processor.drain_once()
    await processor.close()

    assert store.ready_outbox_items() == []
    assert len(alerter.messages) == 1


async def test_5xx_reschedules_with_backoff_instead_of_dropping(tmp_path):
    settings = make_settings(tmp_path)
    store = Store(settings.db_path)
    store.enqueue_outbox("tg:1:1", {"externalId": "tg:1:1"})

    async def handler(request):
        return httpx.Response(500, text="internal error")

    processor = OutboxProcessor(settings, store, client=_client_with_handler(handler))
    await processor.drain_once()
    await processor.close()

    # not removed, but hidden until next_retry_at — ready_outbox_items() is empty right now
    assert store.ready_outbox_items() == []
    row = store._conn.execute(
        "SELECT attempts, next_retry_at FROM outbox WHERE external_id = ?", ("tg:1:1",)
    ).fetchone()
    assert row["attempts"] == 1
    assert row["next_retry_at"] is not None


async def test_network_error_reschedules(tmp_path):
    settings = make_settings(tmp_path)
    store = Store(settings.db_path)
    store.enqueue_outbox("tg:1:1", {"externalId": "tg:1:1"})

    async def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    processor = OutboxProcessor(settings, store, client=_client_with_handler(handler))
    await processor.drain_once()
    await processor.close()

    row = store._conn.execute(
        "SELECT attempts FROM outbox WHERE external_id = ?", ("tg:1:1",)
    ).fetchone()
    assert row["attempts"] == 1


async def test_exhausted_retries_drops_and_alerts(tmp_path):
    settings = make_settings(tmp_path, max_retry_attempts=1)
    store = Store(settings.db_path)
    store.enqueue_outbox("tg:1:1", {"externalId": "tg:1:1"})
    alerter = FakeAlerter()

    async def handler(request):
        return httpx.Response(500, text="internal error")

    processor = OutboxProcessor(settings, store, alerter=alerter, client=_client_with_handler(handler))
    await processor.drain_once()
    await processor.close()

    assert store.ready_outbox_items() == []
    assert any("исчерпаны ретраи" in m for m in alerter.messages)
