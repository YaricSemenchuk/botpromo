from tgparser.models import MessageMeta
from tgparser.store import Store
from tgparser.telegram_client import _message_meta, process_message


def _call(store, message_id, text, chat_id=1, chat_name="ASO Chat RU", sender_name="Ivan", sender_username="ivanp", link="https://t.me/c/1/1", meta=None):
    process_message(
        store,
        chat_id=chat_id,
        message_id=message_id,
        chat_name=chat_name,
        text=text,
        sender_name=sender_name,
        sender_username=sender_username,
        link=link,
        meta=meta,
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


def test_broadcast_is_not_enqueued(tmp_path):
    # Тот же текст, что и в test_catch_enqueues_lead_payload, но постом канала:
    # в CRM он не уходит, а в лог обработанных попадает — чтобы было видно, что
    # именно отсеялось и по какой причине.
    store = Store(tmp_path / "test.db")
    _call(store, 1, "Есть тут те кто ASO могут сделать платно, отпишите в лс",
          meta=MessageMeta(is_post=True))

    assert store.ready_outbox_items() == []
    assert store.is_processed("tg:1:1")


class _FakeUser:
    first_name = "Ivan"


class _FakeChannel:
    title = "ASO Digest"


class _FakeMessage:
    def __init__(self, post=False, fwd_from=None, via_bot_id=None):
        self.post = post
        self.fwd_from = fwd_from
        self.via_bot_id = via_bot_id


def test_message_meta_reads_the_telethon_flags():
    # Признаки формата были доступны на входе и просто выбрасывались.
    assert not _message_meta(_FakeMessage(), _FakeUser()).is_broadcast
    assert _message_meta(_FakeMessage(post=True), _FakeUser()).is_broadcast
    assert _message_meta(_FakeMessage(fwd_from=object()), _FakeUser()).is_broadcast
    assert _message_meta(_FakeMessage(via_bot_id=42), _FakeUser()).is_broadcast
    # Написано от имени канала: username нет, писать «лиду» некуда.
    assert _message_meta(_FakeMessage(), _FakeChannel()).is_broadcast


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


def test_on_lead_fires_only_for_caught_messages(tmp_path):
    # Через этот колбэк отправщик просыпается досрочно: пойманный лид уходит в
    # CRM сразу, а не ждёт следующего тика. На отброшенных будить нечего.
    store = Store(tmp_path / "test.db")
    calls = []

    process_message(
        store,
        chat_id=1,
        message_id=1,
        chat_name="ASO Chat RU",
        text="Есть тут те кто ASO могут сделать платно, отпишите в лс",
        sender_name="Ivan",
        sender_username="ivanp",
        link="https://t.me/c/1/1",
        on_lead=lambda: calls.append("woken"),
    )
    assert calls == ["woken"]

    process_message(
        store,
        chat_id=1,
        message_id=2,
        chat_name="ASO Chat RU",
        text="Всем привет, как дела?",
        sender_name="Ivan",
        sender_username="ivanp",
        link="https://t.me/c/1/2",
        on_lead=lambda: calls.append("woken"),
    )
    assert calls == ["woken"]
