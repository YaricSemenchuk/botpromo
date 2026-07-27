from __future__ import annotations

import re
from typing import Iterable

from ..models import ClassificationResult
from .rules import (
    BARTER_BORDERLINE_MARKERS,
    DIY_META_MARKERS,
    DM_CONTACT_MARKERS,
    JOB_NEGATIVE_MARKERS,
    NON_ASO_PURCHASE_MARKERS,
    PEER_QUESTION_MARKERS,
    PURCHASE_SIGNAL_MARKERS,
    SELLER_NEGATIVE_MARKERS,
    STRONG_INTENT_MARKERS,
    THEMATIC_PATTERNS,
)

_FLAGS = re.IGNORECASE | re.UNICODE


def _compile(patterns: Iterable[str]) -> list[re.Pattern]:
    return [re.compile(p, _FLAGS) for p in patterns]


_THEMATIC = _compile(THEMATIC_PATTERNS)
_STRONG_INTENT = _compile(STRONG_INTENT_MARKERS)
_DM_CONTACT = _compile(DM_CONTACT_MARKERS)
_DIY = _compile(DIY_META_MARKERS)
_SELLER = _compile(SELLER_NEGATIVE_MARKERS)
_JOB = _compile(JOB_NEGATIVE_MARKERS)
_BARTER = _compile(BARTER_BORDERLINE_MARKERS)
_NON_ASO = _compile(NON_ASO_PURCHASE_MARKERS)
_PEER = _compile(PEER_QUESTION_MARKERS)
_PURCHASE = _compile(PURCHASE_SIGNAL_MARKERS)


def _normalize(text: str) -> str:
    return (text or "").replace("ё", "е").replace("Ё", "Е")


def _matches(patterns: list[re.Pattern], text: str) -> tuple:
    return tuple(m.group(0) for p in patterns if (m := p.search(text)))


def classify(text: str) -> ClassificationResult:
    """Rule-based classifier: THEMATIC WORD + INTENT MARKER in one message.

    Decision order (see plan doc for rationale of each step):
    1. job posting or job seeker -> discard, regardless of anything else
    2. buying something that isn't our service (dev accounts, ready-made apps,
       crypto, payout services) -> discard: intent is real, subject is not ours
    3. no thematic word -> discard (off-topic)
    4. diy question ("как лучше указывать ключевые слова") -> catch, tag=diy
    5. question to fellow chat members ("кто как качает ключи", "у кого не
       обновляется статистика") -> discard, UNLESS money is on the table:
       "платно/куплю/бюджет" turns the same question into a request
    6. seller pitch (1st person "делаю/предоставляем") without STRONG buyer
       intent -> discard. A lone "пишите в лс" doesn't count here — sellers
       use that same CTA constantly, so it must not overrule the seller flag.
    7. seller pitch + strong buyer intent both present -> catch, tag=borderline
    8. barter/giveaway markers -> catch, tag=borderline
    9. thematic + (strong intent or DM-contact) -> catch, no tag
    10. thematic only, nothing else -> discard
    """
    normalized = _normalize(text)

    if _matches(_JOB, normalized):
        return ClassificationResult(action="discard")

    if _matches(_NON_ASO, normalized):
        return ClassificationResult(action="discard")

    thematic_hits = _matches(_THEMATIC, normalized)
    if not thematic_hits:
        return ClassificationResult(action="discard")

    diy_hits = _matches(_DIY, normalized)
    if diy_hits:
        return ClassificationResult(
            action="catch", tag="diy", matched_thematic=thematic_hits, matched_intent=diy_hits
        )

    if _matches(_PEER, normalized) and not _matches(_PURCHASE, normalized):
        return ClassificationResult(action="discard")

    strong_intent_hits = _matches(_STRONG_INTENT, normalized)
    seller_hits = _matches(_SELLER, normalized)

    if seller_hits and not strong_intent_hits:
        return ClassificationResult(action="discard")

    if seller_hits and strong_intent_hits:
        return ClassificationResult(
            action="catch", tag="borderline", matched_thematic=thematic_hits, matched_intent=strong_intent_hits
        )

    barter_hits = _matches(_BARTER, normalized)
    if barter_hits:
        return ClassificationResult(
            action="catch", tag="borderline", matched_thematic=thematic_hits, matched_intent=barter_hits
        )

    dm_hits = _matches(_DM_CONTACT, normalized)
    intent_hits = strong_intent_hits + dm_hits
    if intent_hits:
        return ClassificationResult(
            action="catch", tag=None, matched_thematic=thematic_hits, matched_intent=intent_hits
        )

    return ClassificationResult(action="discard")
