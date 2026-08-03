from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

ClassifyAction = Literal["catch", "discard"]


@dataclass(frozen=True)
class MessageMeta:
    """Признаки формата сообщения — то, чего не видно в тексте.

    Классификатор работал на голом тексте и потому не мог отличить объявление
    от реплики: «Вакансия… Резюме в лс» и «ищу подрядчика» приходили к нему
    одинаковыми строками. Здесь ровно те признаки, которые Telegram сообщает
    однозначно; каждый из них означает одно и то же — автора текста в чате нет
    и написать ему нельзя.

    Длину и разметку («Требования:», «Условия:») сюда намеренно не берём:
    единственные длинные структурированные сообщения в нашем трафике — это
    вакансии, а их владелец ловить просил (решение от 27.07.2026).
    """

    is_post: bool = False           # пост канала, а не сообщение человека
    forwarded: bool = False         # репост чужого текста
    via_bot: bool = False           # отправлено через инлайн-бота
    sender_is_channel: bool = False  # написано от имени канала, username нет

    @property
    def is_broadcast(self) -> bool:
        return self.is_post or self.forwarded or self.via_bot or self.sender_is_channel


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
