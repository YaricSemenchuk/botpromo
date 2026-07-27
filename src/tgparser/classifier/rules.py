"""Keyword/pattern lists for the rule-based classifier.

Formula from the spec: THEMATIC WORD + INTENT MARKER in the same message.
These lists are the thing that gets tuned after the pilot launch on 2-3
groups (see plan phase 7) — keep patterns here, not scattered in engine.py.

Patterns are plain regex fragments (no anchors needed beyond \\b), compiled
with re.IGNORECASE | re.UNICODE in engine.py. Text is normalized (lowercase,
ё->е) before matching, so patterns only need to handle "е".
"""

# Тематические слова: ASO/продвижение приложений (RU + EN).
THEMATIC_PATTERNS = [
    r"\bасо\b",
    r"\baso\b",
    r"\bмотив\w*",
    r"\bбот\w*",
    r"\bнакрутк\w*|\bнакрут\w*",
    r"вывод\w*\s+.{0,15}\bтоп\b",
    r"\bключ\w*",
    r"\bпозици\w*",
    r"\bинсталл\w*",
    r"\bустанов\w*",
    r"\bрейтинг\w*",
    r"\bотзыв\w*",
    r"\bпродвижен\w*",
    r"\bаудит\w*",
    r"\bрепутац\w*",
    r"\bконкурент\w*",
    r"\bскриншот\w*",
    r"\bиконк\w*",
    r"текстов\w*\s+.{0,15}оптимизац\w*",
    r"график\w*\s+.{0,15}оптимизац\w*",
    r"custom\s*product\s*page\w*",
    r"кастом\w*\s*продакт\w*\s*пейдж\w*",
    r"in-?app\s*event\w*",
    r"инап\w*\s*ивент\w*",
    r"app\s*store",
    r"google\s*play",
    r"\bстор[ае]?\b",
    r"\bприлк\w*",
    r"\bприла\b",
    r"\bприложени\w*",
    r"\bkeyapp\b",
    r"\bкейапп\w*",
    # EN
    r"keyword\s+install\w*",
    r"motivated\s+(install|traffic)\w*",
    r"app\s+promotion",
    r"boost\w*\s+(ranking|position)\w*",
    r"\breview\w*\b",
    r"\brating\w*\b",
    r"app\s*store\s*optimization",
]

# Маркеры намерения: кто-то ИЩЕТ исполнителя/поставщика. "Сильные" — однозначно
# сигнализируют вопрос/поиск (не встречаются в обычной рекламе услуг).
STRONG_INTENT_MARKERS = [
    r"\bкто\b.{0,25}\b(делает|дела[ею]т)\b",
    r"\bкто\b.{0,25}\b(может|могут)\b.{0,15}\bсдела\w*\b",
    r"\bплатно\b",
    r"где\s+(можно\s+)?(купить|закупить)",
    r"(посовету\w*|подскаж\w*).{0,15}\bкто\b",
    r"у\s+кого\s+можно",
    r"у\s+кого\s+(есть\s+)?свой\s+сервис",
    r"\bкто\b\s+(предоставляет|обеспечивает)",
    r"ком\w*\s+интересно.{0,15}пиш\w*",
    # EN
    r"who\s+can\s+do",
    r"looking\s+for",
    r"where\s+to\s+(buy|purchase)",
    r"\bpaid\b",
]

# "Слабые" маркеры — просьба написать в лс. Сама по себе продавцы используют
# её как call-to-action не реже покупателей, поэтому она НЕ должна одна
# перевешивать SELLER_NEGATIVE_MARKERS (см. engine.classify) — но всё ещё
# считается намерением для обычного thematic+intent совпадения.
DM_CONTACT_MARKERS = [
    r"(отпиш\w*|напиш\w*)\w*\s*(в\s*)?(лс|личк\w*)",
    r"\bdm\s+me\b",
]

# DIY: владелец прилы делает ASO сам и спрашивает "как правильно" — тёплый лид.
DIY_META_MARKERS = [
    r"как\s+(лучше|правильно)\s+(указывать|писать|делать|расставлять|прописывать)",
]

# Self-referential (1st person) service pitch — "я/мы делаем/предоставляем X".
# Намеренно не пересекается с "кто предоставляет" / "у кого свой сервис"
# (там 3-е лицо / вопрос) — это главный фильтр продавцов из спеки.
SELLER_NEGATIVE_MARKERS = [
    r"предоставля(?:ем|ю)\b",
    r"\bделаю\b",
    r"дела(?:ем)\b",
    r"оказыва(?:ем|ю)\b",
    r"\bпрода(?:ём|ем|ю)\b",
    r"наш\w*\s+сервис",
    r"\bпрайс\b",
    r"\bпортфолио\b",
    r"цена\s+от\b",
    r"от\s+\d+\s*(руб|₽|\$|usd)",
]

# Вакансии в штат — не лиды.
JOB_NEGATIVE_MARKERS = [
    r"в\s+(команду|штат)\b",
    r"\bоклад\b",
    r"\bвакансия\b",
    r"зарплата\s+от",
]

# Бартер/розыгрыши — пограничное, решает сейл.
BARTER_BORDERLINE_MARKERS = [
    r"отзыв\s+за\s+отзыв",
    r"взаимн\w*\s+подпис\w*",
    r"\bрозыгрыш\w*",
    r"\bконкурс\b(?!ент)",
]
