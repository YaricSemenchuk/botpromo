from tgparser.store import Store


def test_processed_idempotency(tmp_path):
    store = Store(tmp_path / "test.db")
    assert not store.is_processed("tg:1:1")

    store.record_processed("tg:1:1", chat_id=1, message_id=1, action="catch", tag=None)
    assert store.is_processed("tg:1:1")

    # re-recording the same external_id must not raise or duplicate
    store.record_processed("tg:1:1", chat_id=1, message_id=1, action="catch", tag=None)
    assert store.is_processed("tg:1:1")


def test_outbox_enqueue_and_ready_items(tmp_path):
    store = Store(tmp_path / "test.db")
    payload = {"source": "tg", "externalId": "tg:1:1", "name": "Test", "text": "hi", "link": "x"}

    store.enqueue_outbox("tg:1:1", payload)
    items = store.ready_outbox_items()
    assert len(items) == 1
    assert items[0].external_id == "tg:1:1"
    assert items[0].payload == payload
    assert items[0].attempts == 0

    store.remove_from_outbox("tg:1:1")
    assert store.ready_outbox_items() == []


def test_outbox_reschedule_hides_item_until_retry_time(tmp_path):
    from datetime import datetime, timedelta, timezone

    store = Store(tmp_path / "test.db")
    store.enqueue_outbox("tg:1:1", {"externalId": "tg:1:1"})

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    store.reschedule_outbox("tg:1:1", future, "500 server error")

    assert store.ready_outbox_items() == []

    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    store.reschedule_outbox("tg:1:1", past, "500 server error")
    items = store.ready_outbox_items()
    assert len(items) == 1
    assert items[0].attempts == 2
    assert items[0].last_error == "500 server error"


def test_checkpoints_roundtrip(tmp_path):
    store = Store(tmp_path / "test.db")
    assert store.get_checkpoint(42) is None

    store.set_checkpoint(42, 100)
    assert store.get_checkpoint(42) == 100

    store.set_checkpoint(42, 150)
    assert store.get_checkpoint(42) == 150
