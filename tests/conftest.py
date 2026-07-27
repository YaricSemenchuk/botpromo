from pathlib import Path

from tgparser.config import Settings


def make_settings(tmp_path: Path, **overrides) -> Settings:
    defaults = dict(
        tg_api_id=1,
        tg_api_hash="hash",
        tg_session_string="session",
        crm_endpoint="https://crm.example/api/inbound/lead",
        inbound_token="test-token",
        dry_run=False,
        db_path=tmp_path / "test.db",
        groups_path=tmp_path / "groups.yaml",
        alert_bot_token=None,
        alert_chat_id=None,
        http_timeout_seconds=10.0,
        max_retry_attempts=8,
        retry_backoff_base_seconds=2.0,
        retry_backoff_max_seconds=300.0,
    )
    defaults.update(overrides)
    return Settings(**defaults)
