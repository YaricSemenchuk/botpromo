import httpx

from tgparser.alerts import NullAlerter, TelegramBotAlerter, build_alerter

from .conftest import make_settings


async def test_null_alerter_does_not_raise():
    await NullAlerter().notify("test message")


async def test_build_alerter_returns_null_when_unconfigured(tmp_path):
    settings = make_settings(tmp_path, alert_bot_token=None, alert_chat_id=None)
    assert isinstance(build_alerter(settings), NullAlerter)


async def test_build_alerter_returns_telegram_bot_when_configured(tmp_path):
    settings = make_settings(tmp_path, alert_bot_token="123:abc", alert_chat_id="42")
    assert isinstance(build_alerter(settings), TelegramBotAlerter)


async def test_telegram_bot_alerter_posts_expected_payload():
    captured = {}

    async def handler(request):
        captured["url"] = str(request.url)
        captured["body"] = request.content
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    alerter = TelegramBotAlerter("123:abc", "42", client=client)
    await alerter.notify("hello")
    await alerter.close()

    assert captured["url"] == "https://api.telegram.org/bot123:abc/sendMessage"
    assert b"hello" in captured["body"]
    assert b"42" in captured["body"]


async def test_telegram_bot_alerter_swallows_http_errors():
    async def handler(request):
        return httpx.Response(500, text="boom")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    alerter = TelegramBotAlerter("123:abc", "42", client=client)
    await alerter.notify("hello")  # must not raise
    await alerter.close()
