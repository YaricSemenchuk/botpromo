import pytest

from tgparser.classifier import classify

# Эталонные примеры улова — дословно из стартового пакета.
CATCH_EXAMPLES = [
    "Есть тут те кто ASO могут сделать платно и качественно отпишите в лс",
    "Подскажите, пожалуйста где можно закупить мотив, кроме как keyapp. "
    "Если тут есть у кого свой сервис или предоставляет услуги, то напишете в лс",
    "кто-нибудь знает, кто обеспечивает хорошие установки ключевых слов?",
    "у кого можно купить мотивированные инсталлы или ботов для движения позиций Ipad?",
    "Есть прилка в сторе Aviator. Кому интересно, пишите.",
]

DIY_EXAMPLE = (
    "Ребят подскажите как лучше указывать ключевые слова в ASO App Store: "
    "вот так кючевоеслово,слово или ключевоеслово, слово?"
)

# Зеркальный мусор из того же раздела спеки — продавцы, вакансии, болталка.
SELLER_EXAMPLES = [
    "Делаю ASO быстро и качественно, портфолио и прайс в лс",
    "Наш сервис по мотиву — лучшие цены на рынке, пишите в лс",
    "Оказываем услуги по продвижению приложений уже 5 лет, портфолио по запросу",
]

JOB_EXAMPLE = "Ищем ASO-специалиста в команду, оклад от 150000, пишите в лс"

OFFTOPIC_EXAMPLES = [
    "Кто-нибудь смотрел новый апдейт App Store сегодня?",
    "Всем привет, как дела?",
]

BARTER_EXAMPLE = "Отзыв за отзыв, кому надо? Пишите в лс"


@pytest.mark.parametrize("text", CATCH_EXAMPLES)
def test_catch_examples_are_caught_without_tag(text):
    result = classify(text)
    assert result.action == "catch"
    assert result.tag is None


def test_diy_example_is_caught_with_diy_tag():
    result = classify(DIY_EXAMPLE)
    assert result.action == "catch"
    assert result.tag == "diy"


@pytest.mark.parametrize("text", SELLER_EXAMPLES)
def test_seller_pitches_are_discarded(text):
    result = classify(text)
    assert result.action == "discard"


def test_job_posting_is_discarded_even_with_dm_cta():
    result = classify(JOB_EXAMPLE)
    assert result.action == "discard"


@pytest.mark.parametrize("text", OFFTOPIC_EXAMPLES)
def test_offtopic_messages_are_discarded(text):
    result = classify(text)
    assert result.action == "discard"


def test_barter_is_caught_as_borderline():
    result = classify(BARTER_EXAMPLE)
    assert result.action == "catch"
    assert result.tag == "borderline"


def test_seller_pitch_with_strong_buyer_intent_is_borderline():
    text = (
        "Мы предоставляем услуги по мотиву, но если кто может сделать дешевле "
        "и платно готов обсудить — пишите в лс"
    )
    result = classify(text)
    assert result.action == "catch"
    assert result.tag == "borderline"


def test_empty_text_is_discarded():
    assert classify("").action == "discard"
