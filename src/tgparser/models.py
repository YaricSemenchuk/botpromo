from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

ClassifyAction = Literal["catch", "discard"]


@dataclass(frozen=True)
class IncomingMessage:
    chat_id: int
    message_id: int
    chat_name: str
    text: str
    sender_name: str
    sender_username: Optional[str]
    link: str

    @property
    def external_id(self) -> str:
        return f"tg:{self.chat_id}:{self.message_id}"


@dataclass(frozen=True)
class ClassificationResult:
    action: ClassifyAction
    tag: Optional[str] = None  # "diy" | "borderline" | None
    matched_thematic: tuple = ()
    matched_intent: tuple = ()


@dataclass(frozen=True)
class LeadPayload:
    source: str
    external_id: str
    name: str
    text: str
    telegram: Optional[str]
    link: str
    meta: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        body = {
            "source": self.source,
            "externalId": self.external_id,
            "name": self.name,
            "text": self.text,
            "link": self.link,
        }
        if self.telegram:
            body["telegram"] = self.telegram
        if self.meta:
            body["meta"] = self.meta
        return body
