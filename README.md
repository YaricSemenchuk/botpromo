# tgparser — TG-парсер лидов для Promobile CRM

Мониторит ASO-шные Telegram-группы, детектит запросы на ASO/продвижение
приложений по правилам (`src/tgparser/classifier`) и шлёт каждое совпадение
одним POST в CRM (контракт — см. стартовый пакет). Классификация целиком на
стороне парсера, точность важнее полноты.

Полный план и обоснование решений — в `/Users/yaroslavsemianchuk/.claude/plans/fancy-spinning-penguin.md`.

## Быстрый старт (локально)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Тесты (`tests/`) не требуют ни Telegram, ни CRM — классификатор, стор и
sender протестированы офлайн на моках/эталонных примерах из спеки.

## Что нужно, чтобы включить реальный мониторинг

1. **Новый Telegram-номер** — заводится специально под этот userbot, должен
   вступить во все целевые группы до запуска.
2. **`TG_API_ID` / `TG_API_HASH`** — https://my.telegram.org, на этот номер.
3. **`TG_SESSION_STRING`** — разовый интерактивный логин:
   ```bash
   python scripts/generate_session.py
   ```
   Полученную строку — в `TG_SESSION_STRING` (Railway env, секрет, не в код).
4. **`config/groups.yaml`** — реальный список групп от Андрея (см. пример в файле).
5. **`INBOUND_TOKEN`** — от Андрея, нужен только когда эндпоинт CRM включат
   (сейчас 404). До этого держим `DRY_RUN=true`.

Полный список переменных — `.env.example`.

## DRY_RUN — можно запускать уже сейчас

`DRY_RUN=true` (по умолчанию): классификатор работает на реальном трафике,
результат логируется и пишется в локальную SQLite (`data/tgparser.db`), но
POST в CRM не уходит. Так можно копить примеры и подкручивать
`classifier/rules.py`, не дожидаясь включения эндпоинта.

## Тест контракта, когда эндпоинт включат

```bash
python - <<'EOF'
import asyncio, httpx
from tgparser.config import load_settings
from tgparser.models import LeadPayload
from tgparser.sender import send_now

async def main():
    settings = load_settings()
    payload = LeadPayload(source="tg", external_id="tg:test:1", name="Test",
                           text="test", telegram=None, link="https://t.me/test/1")
    async with httpx.AsyncClient() as client:
        r = await send_now(client, settings, payload)
        print(r.status_code, r.json())
        r2 = await send_now(client, settings, payload)  # повтор -> duplicate:true
        print(r2.status_code, r2.json())

asyncio.run(main())
EOF
```

## Запуск сервиса

```bash
python -m tgparser.main
```

## Деплой на Railway

- Билд по `Dockerfile` (см. `railway.json`).
- Volume на `/data` (для `data/tgparser.db` — outbox и чекпоинты должны
  переживать редеплой) — подключается через Railway dashboard.
- Секреты — все переменные из `.env.example`, кроме `DB_PATH`/`GROUPS_PATH`
  (уже выставлены в Dockerfile).

## Структура

```
src/tgparser/
  config.py           # env + config/groups.yaml
  models.py            # MessageMeta / ClassificationResult / LeadPayload
  classifier/
    rules.py           # тематические слова / маркеры намерения / стоп-листы — сюда лезть при подкрутке
    engine.py           # classify(text, meta) -> ClassificationResult
  store.py              # SQLite: идемпотентность, outbox, чекпоинты
  sender.py              # POST в CRM, retry/backoff, DRY_RUN
  alerts.py               # Telegram-бот для алертов на 401/422/исчерпанные ретраи
  telegram_client.py       # Telethon: подписка на группы, catch-up, process_message()
  main.py                   # сборка всего, entrypoint
scripts/generate_session.py # разовый логин -> TG_SESSION_STRING
```

## Порядок боевого запуска

См. план (`fancy-spinning-penguin.md`, разделы «Порядок реализации»):
build → DRY_RUN на Railway на реальных группах → тест контракта
(`tg:test:1` create/duplicate) → `DRY_RUN=false` → 2-3 группы → смотрим
качество с Андреем → тюним `classifier/rules.py` → расширяем `groups.yaml`.
