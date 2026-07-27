from tgparser.store import Store
from tgparser.telegram_client import process_message


def _call(store, message_id, text, chat_id=1, chat_name="ASO Chat RU", sender_name="Ivan", sender_username="ivanp", link="https://t.me/c/1/1"):
    process_message(
        store,
        chat_id=chat_id,
        message_id=message_id,
        chat_name=chat_name,
        text=text,
        sender_name=sender_name,
        sender_username=sender_username,
        link=link,
    )


def test_catch_enqueues_lead_payload(tmp_path):
    store = Store(tmp_path / "test.db")
    _call(store, 1, "Есть тут те кто ASO могут сделать платно, отпишите в лс")

    items = store.ready_outbox_items()
    assert len(items) == 1
    payload = items[0].payload
    assert payload["source"] == "tg"
    assert payload["externalId"] == "tg:1:1"
    assert payload["name"] == "Ivan"
    assert payload["telegram"] == "@ivanp"
    assert payload["meta"]["group"] == "ASO Chat RU"
    assert "tag" not in payload["meta"]


def test_diy_tag_is_included_in_meta(tmp_path):
    store = Store(tmp_path / "test.db")
    _call(store, 1, "Подскажите как лучше указывать ключевые слова в ASO App Store")

    items = store.ready_outbox_items()
    assert items[0].payload["meta"]["tag"] == "diy"


def test_discard_does_not_enqueue(tmp_path):
    store = Store(tmp_path / "test.db")
    _call(store, 1, "Всем привет, как дела?")

    assert store.ready_outbox_items() == []
    assert store.is_processed("tg:1:1")


def test_same_message_processed_twice_is_a_no_op(tmp_path):
    store = Store(tmp_path / "test.db")
    text = "кто может сделать ASO платно?"

    _call(store, 1, text)
    _call(store, 1, text)  # e.g. catch-up racing with the live event handler

    assert len(store.ready_outbox_items()) == 1


def test_checkpoint_never_moves_backward(tmp_path):
    store = Store(tmp_path / "test.db")
    _call(store, 5, "Всем привет")
    assert store.get_checkpoint(1) == 5

    _call(store, 3, "Всем привет")  # an older message arriving out of order
    assert store.get_checkpoint(1) == 5
