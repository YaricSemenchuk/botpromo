from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GROUPS_PATH = REPO_ROOT / "config" / "groups.yaml"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "tgparser.db"
DEFAULT_CRM_ENDPOINT = "https://pm-crm-production.up.railway.app/api/inbound/lead"


def _env(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.environ.get(name, default)
    if value is not None:
        # Dashboard-pasted secrets routinely pick up a trailing newline/space
        # (e.g. copying a printed line including its line terminator) — a
        # stray char is invisible but breaks exact-length-sensitive parsing
        # like Telethon's StringSession. Strip defensively for every var.
        value = value.strip()
    if required and not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Group:
    chat: str
    name: str


@dataclass(frozen=True)
class Settings:
    tg_api_id: int
    tg_api_hash: str
    tg_session_string: str
    crm_endpoint: str
    inbound_token: str
    dry_run: bool
    db_path: Path
    groups_path: Path
    alert_bot_token: str | None
    alert_chat_id: str | None
    http_timeout_seconds: float
    max_retry_attempts: int
    retry_backoff_base_seconds: float
    retry_backoff_max_seconds: float

    @property
    def groups(self) -> list[Group]:
        return load_groups(self.groups_path)


def load_groups(path: Path) -> list[Group]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [
        Group(chat=str(item["chat"]), name=str(item.get("name", item["chat"])))
        for item in raw
    ]


def load_settings() -> Settings:
    """Reads process env into a Settings instance. Only called from the
    running service (main.py / scripts) — never from unit tests, so the
    required-env checks below are safe to enforce unconditionally."""
    dry_run = _env_bool("DRY_RUN", default=True)
    return Settings(
        tg_api_id=int(_env("TG_API_ID", required=True)),
        tg_api_hash=_env("TG_API_HASH", required=True) or "",
        tg_session_string=_env("TG_SESSION_STRING", required=True) or "",
        crm_endpoint=_env("CRM_ENDPOINT", default=DEFAULT_CRM_ENDPOINT) or DEFAULT_CRM_ENDPOINT,
        inbound_token=_env("INBOUND_TOKEN", default="", required=not dry_run) or "",
        dry_run=dry_run,
        db_path=Path(_env("DB_PATH", default=str(DEFAULT_DB_PATH)) or DEFAULT_DB_PATH),
        groups_path=Path(_env("GROUPS_PATH", default=str(DEFAULT_GROUPS_PATH)) or DEFAULT_GROUPS_PATH),
        alert_bot_token=_env("ALERT_BOT_TOKEN"),
        alert_chat_id=_env("ALERT_CHAT_ID"),
        http_timeout_seconds=float(_env("HTTP_TIMEOUT_SECONDS", default="10") or 10),
        max_retry_attempts=int(_env("MAX_RETRY_ATTEMPTS", default="8") or 8),
        retry_backoff_base_seconds=float(_env("RETRY_BACKOFF_BASE_SECONDS", default="2") or 2),
        retry_backoff_max_seconds=float(_env("RETRY_BACKOFF_MAX_SECONDS", default="300") or 300),
    )
