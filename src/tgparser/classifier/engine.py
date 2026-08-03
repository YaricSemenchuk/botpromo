from __future__ import annotations

import re
from typing import Iterable

from ..models import ClassificationResult, MessageMeta
from .rules import (
    BARTER_BORDERLINE_MARKERS,
    DIY_META_MARKERS,
    DM_CONTACT_MARKERS,
    HIRING_MARKERS,
    JOB_BOARD_MARKERS,
    JOB_SEEKER_MARKERS,
    NON_ASO_PURCHASE_MARKERS,
    OUR_ROLE_PATTERNS,
    PEER_QUESTION_MARKERS,
    PURCHASE_SIGNAL_MARKERS,
    REQUEST_INTENT_MARKERS,
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
_HIRING = _compile(HIRING_MARKERS)
_SEEKER = _compile(JOB_SEEKER_MARKERS)
_JOB_BOARD = _compile(JOB_BOARD_MARKERS)
_OUR_ROLE = _compile(OUR_ROLE_PATTERNS)
_BARTER = _compile(BARTER_BORDERLINE_MARKERS)
_NON_ASO = _compile(NON_ASO_PURCHASE_MARKERS)
_PEER = _compile(PEER_QUESTION_MARKERS)
_PURCHASE = _compile(PURCHASE_SIGNAL_MARKERS)
_REQUEST = _compile(REQUEST_INTENT_MARKERS)


def _normalize(text: str) -> str:
    return (text or "").replace("ё", "е").replace("Ё", "Е")


def _matches(patterns: list[re.Pattern], text: str) -> tuple:
    return tuple(m.group(0) for p in patterns if (m := p.search(text)))


def classify(text: str, meta: MessageMeta | None = None) -> ClassificationResult:
    """Rule-based classifier: THEMATIC WORD + INTENT MARKER in one message.

    Decision order (see plan doc for rationale of each step):
    -1. broadcast (channel post, repost, sent via a bot) -> discard, tag=post.
        This one is about the medium, not the content, so it comes first: the
        text of an announcement is indistinguishable from a request, and there
        is nobody in the chat to reply to. The tag is kept so the reason stays
        visible in the processed log while tuning.
    0. job seeker -> discard: someone offering their own labour is not a buyer
    1. buying something that isn't our service (dev accounts, ready-made apps,
       crypto, payout services) -> discard: intent is real, subject is not ours
    2. no thematic word -> discard (off-topic)
    3. company hiring -> catch with tag=vacancy IF the role is ours (ASO/ASA/UA):
       that company needs exactly the work we sell and can outsource it instead
       of staffing it. Hiring for anything else -> discard.
    4. diy question ("как лучше указывать ключевые слова") -> catch, tag=diy
    5. question to fellow chat members ("кто как качает ключи", "у кого не
       обновляется статистика") -> discard, UNLESS money is on the table or a
       performer is being sought: "платно/куплю/бюджет/ищу подрядчика" turns
       the same question into a request
    6. seller pitch (1st person "делаю/предоставляем") without STRONG buyer
       intent -> discard. A lone "пишите в лс" doesn't count here — sellers
       use that same CTA constantly, so it must not overrule the seller flag.
    7. seller pitch + strong buyer intent both present -> catch, tag=borderline
    8. barter/giveaway markers -> catch, tag=borderline
    9. thematic + (strong intent or DM-contact) -> catch, no tag
    10. thematic only, nothing else -> discard

    Hiring sits AFTER the thematic gate on purpose: it is the only branch that
    can discard on its own, and it used to run first, so a request phrased as
    "ищу дизайнера для скриншотов" was read as a vacancy for someone else's
    role and dropped. Every role we sell is also a thematic word (enforced by
    test_our_role_vocabulary_is_covered_by_thematic_vocabulary), so no real
    vacancy is lost by gating on the topic first.
    """
    if meta is not None and meta.is_broadcast:
        return ClassificationResult(action="discard", tag="post")

    normalized = _normalize(text)

    if _matches(_SEEKER, normalized) or _matches(_JOB_BOARD, normalized):
        return ClassificationResult(action="discard")

    if _matches(_NON_ASO, normalized):
        return ClassificationResult(action="discard")

    thematic_hits = _matches(_THEMATIC, normalized)
    if not thematic_hits:
        return ClassificationResult(action="discard")

    hiring_hits = _matches(_HIRING, normalized)
    if hiring_hits:
        role_hits = _matches(_OUR_ROLE, normalized)
        if role_hits:
            return ClassificationResult(
                action="catch", tag="vacancy", matched_thematic=role_hits, matched_intent=hiring_hits
            )
        return ClassificationResult(action="discard")

    diy_hits = _matches(_DIY, normalized)
    if diy_hits:
        return ClassificationResult(
            action="catch", tag="diy", matched_thematic=thematic_hits, matched_intent=diy_hits
        )

    if _matches(_PEER, normalized) and not (
        _matches(_PURCHASE, normalized) or _matches(_REQUEST, normalized)
    ):
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
