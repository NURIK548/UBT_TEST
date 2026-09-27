import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import flet as ft

# ---------------------------------------------------------------------------
# Constants & Configuration
# ---------------------------------------------------------------------------
QUIZZES_FILE = "quizzes.json"
USERS_FILE = "users.json"
SETTINGS_FILE = "settings.json"
TEACHER_PASSWORD = "admin"
DEFAULT_TEST_MINUTES = 40
POINTS_BASE = 10

QTYPE_SINGLE = "single"
QTYPE_MULTI = "multi"
QTYPE_MATCH = "match"

PROFANITY_MSG = "Құрамында бейәдеп сөздер бар! Өтініш, мәтінді тексеріңіз."
PRACTICE_DISCLAIMER = "Бұл — дайындық және жаттығу режимі. Нәтиже ұпайлары сақталады."

THEMES = {
    "slate": {
        "name": "Slate Blue",
        "bg": "#0f172a",
        "card": "#1e293b",
        "card_alt": "#334155",
        "accent": "#38bdf8",
        "purple": "#c084fc",
        "green": "#4ade80",
        "red": "#f87171",
        "amber": "#fbbf24",
        "text": "#f8fafc",
        "muted": "#94a3b8",
        "border": "#475569",
    },
    "emerald": {
        "name": "Emerald Night",
        "bg": "#064e3b",
        "card": "#047857",
        "card_alt": "#065f46",
        "accent": "#34d399",
        "purple": "#a78bfa",
        "green": "#10b981",
        "red": "#f87171",
        "amber": "#f59e0b",
        "text": "#ecfdf5",
        "muted": "#a7f3d0",
        "border": "#059669",
    },
    "light": {
        "name": "Light Clean",
        "bg": "#f8fafc",
        "card": "#ffffff",
        "card_alt": "#f1f5f9",
        "accent": "#0284c7",
        "purple": "#7e22ce",
        "green": "#16a34a",
        "red": "#dc2626",
        "amber": "#d97706",
        "text": "#0f172a",
        "muted": "#64748b",
        "border": "#cbd5e1",
    },
}


class Palette:
    def __init__(self):
        self.apply("slate")

    def apply(self, key: str) -> None:
        t = THEMES.get(key, THEMES["slate"])
        self.key = key if key in THEMES else "slate"
        self.bg = t["bg"]
        self.card = t["card"]
        self.card_alt = t["card_alt"]
        self.accent = t["accent"]
        self.purple = t["purple"]
        self.green = t["green"]
        self.red = t["red"]
        self.amber = t["amber"]
        self.text = t["text"]
        self.muted = t["muted"]
        self.border = t["border"]


P = Palette()


def _storage_dir() -> Path:
    try:
        data_dir = Path(os.environ.get("FLET_APP_STORAGE_DATA", ".")).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    except OSError:
        return Path(".").resolve()


def _path(name: str) -> Path:
    return _storage_dir() / name


def _icon(name: str, fallback: str = "circle"):
    icons = getattr(ft, "Icons", None)
    if icons is not None and hasattr(icons, name):
        return getattr(icons, name)
    legacy = getattr(ft, "icons", None)
    if legacy is not None and hasattr(legacy, name):
        return getattr(legacy, name)
    if icons is not None and hasattr(icons, fallback.upper()):
        return getattr(icons, fallback.upper())
    return fallback


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass
class Choice:
    text: str
    is_correct: bool = False


@dataclass
class Question:
    text: str
    qtype: str = QTYPE_SINGLE
    choices: list[Choice] = field(default_factory=list)
    explanation: str = ""
    subject: str = ""
    match_left: list[str] = field(default_factory=list)
    match_right: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "qtype": self.qtype,
            "explanation": self.explanation,
            "subject": self.subject,
            "choices": [{"text": c.text, "is_correct": c.is_correct} for c in self.choices],
            "match_left": list(self.match_left),
            "match_right": list(self.match_right),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Question":
        choices = [
            Choice(text=str(c.get("text", "")), is_correct=bool(c.get("is_correct", False)))
            for c in data.get("choices", [])
        ]
        qtype = str(data.get("qtype") or data.get("type") or QTYPE_SINGLE)
        if qtype not in (QTYPE_SINGLE, QTYPE_MULTI, QTYPE_MATCH):
            qtype = QTYPE_MULTI if sum(1 for c in choices if c.is_correct) > 1 else QTYPE_SINGLE
        return Question(
            text=str(data.get("text", "")),
            qtype=qtype,
            choices=choices,
            explanation=str(data.get("explanation", "")),
            subject=str(data.get("subject", "")),
            match_left=[str(x) for x in data.get("match_left", [])],
            match_right=[str(x) for x in data.get("match_right", [])],
        )


@dataclass
class Quiz:
    id: str
    title: str
    description: str
    author: str
    questions: list[Question] = field(default_factory=list)
    subject_pair: str = ""
    created_at: float = field(default_factory=time.time)
    is_official: bool = False
    duration_minutes: int = DEFAULT_TEST_MINUTES

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "author": self.author,
            "subject_pair": self.subject_pair,
            "created_at": self.created_at,
            "is_official": self.is_official,
            "duration_minutes": self.duration_minutes,
            "questions": [q.to_dict() for q in self.questions],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Quiz":
        questions = [Question.from_dict(q) for q in data.get("questions", [])]
        try:
            minutes = int(data.get("duration_minutes", DEFAULT_TEST_MINUTES))
        except (TypeError, ValueError):
            minutes = DEFAULT_TEST_MINUTES
        minutes = max(1, min(minutes, 480))
        return Quiz(
            id=str(data.get("id", f"quiz_{int(time.time())}")),
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            author=str(data.get("author", "")),
            questions=questions,
            subject_pair=str(data.get("subject_pair", "")),
            created_at=float(data.get("created_at", time.time())),
            is_official=bool(data.get("is_official", False)),
            duration_minutes=minutes,
        )


# ---------------------------------------------------------------------------
# Profanity filter (Kazakh + Russian)
# ---------------------------------------------------------------------------
_BAD_PHRASES: list[str] = [
    "еб твою", "ит бала", "мал бас", "құдай атсын", "кудай атсын",
    "жаман сөз", "анаңды с", "шешеңді с", "амды с",
]

_BAD_WORDS: list[str] = [
    "блядь", "блять", "бля", "хуй", "хуя", "хуе", "хуи", "пизда", "пизде", "пизду",
    "пизд", "ебать", "ебал", "ебан", "ебл", "сука", "суки", "сучк", "мудак", "мудила",
    "гандон", "гондон", "залупа", "залуп", "дроч", "педик", "пидор", "пидар", "пидр",
    "шлюха", "шлюх", "еблан", "долбоеб", "долбоёб", "мразь", "мразот", "дебил",
    "идиот", "тварь", "сволочь", "падла", "херня", "похер", "нахуй", "нахер",
    "охуе", "охуи", "выеб", "заеб", "проеб", "уеб", "қотақ", "котақ", "қотак",
    "котак", "жексен", "жексің", "шешеңді", "шешенді", "анаңды", "сіксең", "сиксең",
    "сікейін", "сикейін", "сөгіс", "қарғыс", "итбала", "малбас", "доңыз", "доныз",
    "шөреке", "шореке", "blyat", "blyad", "bljad", "pizda", "ebat", "suka", "mudak",
    "pidor", "pidar", "nahui", "nahuy", "qotaq", "sheshendi", "anandy", "sikseyin",
]

_WORD_CHARS = r"0-9A-Za-zА-Яа-яЁёӘәІіҢңҒғҮүҰұҚқӨөҺһ"


def contains_bad_words(text: str) -> bool:
    if not text or not str(text).strip():
        return False
    original = str(text)
    normalized = original.lower().replace("ё", "е").replace("Ё", "е")
    compact = re.sub(r"[\s.*_\-]+", "", normalized)

    for phrase in _BAD_PHRASES:
        p = phrase.lower().replace("ё", "е")
        if p in normalized:
            return True

    for word in _BAD_WORDS:
        w = word.lower().replace("ё", "е")
        pattern = rf"(?<![{_WORD_CHARS}]){re.escape(w)}(?![{_WORD_CHARS}])"
        if re.search(pattern, normalized, re.IGNORECASE | re.UNICODE):
            return True
        if len(w) >= 4 and w in compact:
            return True
    return False


def validate_quiz_content(*texts: str, questions: Optional[list[Question]] = None) -> Optional[str]:
    for t in texts:
        if contains_bad_words(t or ""):
            return PROFANITY_MSG
    for q in questions or []:
        if contains_bad_words(q.text) or contains_bad_words(q.explanation):
            return PROFANITY_MSG
        for c in q.choices:
            if contains_bad_words(c.text):
                return PROFANITY_MSG
        for item in list(q.match_left) + list(q.match_right):
            if contains_bad_words(item):
                return PROFANITY_MSG
    return None


# ---------------------------------------------------------------------------
# Subjects & official banks
# ---------------------------------------------------------------------------
SUBJECT_PAIRS: list[tuple[str, str, str]] = [
    ("01", "Математика", "Физика"),
    ("02", "Математика", "География"),
    ("03", "Математика", "Ағылшын тілі"),
    ("04", "Математика", "Информатика"),
    ("05", "Биология", "Химия"),
    ("06", "Биология", "География"),
    ("07", "Химия", "Физика"),
    ("08", "Тарих", "География"),
    ("09", "Тарих", "Ағылшын тілі"),
    ("10", "География", "Шет тілі"),
    ("11", "Дүниежүзі тарихы", "Адам. Қоғам. Құқық"),
    ("12", "Қазақ тілі мен әдебиеті", "Тарих"),
    ("13", "Орыс тілі мен әдебиеті", "Тарих"),
    ("14", "Физика", "Информатика"),
    ("15", "Информатика", "География"),
]

ELECTIVE_SUBJECTS = [
    "Математика", "Физика", "Информатика", "Химия", "Биология", "Тарих", "География", "Ағылшын тілі"
]


def _q_single(text: str, options: list[str], correct: int, expl: str, subject: str) -> Question:
    return Question(
        text=text,
        qtype=QTYPE_SINGLE,
        choices=[Choice(t, is_correct=(i == correct)) for i, t in enumerate(options)],
        explanation=expl,
        subject=subject,
    )


def _q_multi(text: str, options: list[str], correct: list[int], expl: str, subject: str) -> Question:
    correct_set = set(correct)
    return Question(
        text=text,
        qtype=QTYPE_MULTI,
        choices=[Choice(t, is_correct=(i in correct_set)) for i, t in enumerate(options)],
        explanation=expl,
        subject=subject,
    )


def _q_match(text: str, left: list[str], right: list[str], expl: str, subject: str) -> Question:
    return Question(
        text=text,
        qtype=QTYPE_MATCH,
        match_left=left,
        match_right=right,
        explanation=expl,
        subject=subject,
    )


def question_bank() -> dict[str, list[Question]]:
    return {
        "Математика": [
            _q_single("2x + 5 = 17 теңдеуінің шешімі қандай?", ["x = 4", "x = 6", "x = 5", "x = 7"], 1, "2x = 12 ⇒ x = 6", "Математика"),
            _q_single("Үшбұрыштың ішкі бұрыштарының қосындысы неге тең?", ["90°", "180°", "270°", "360°"], 1, "Евклидтік геометрияда қосынды 180°.", "Математика"),
            _q_multi("Қай өрнектер 12-ге тең? (Көп жауапты сұрақ)", ["3×4", "2+8", "24÷2", "5×3"], [0, 2], "3×4=12 және 24÷2=12.", "Математика"),
            _q_match("Сәйкестендіру тесті: формула мен атау", ["a²+b²=c²", "S=πr²", "P=2(a+b)", "V=abc"], ["Пифагор теоремасы", "Шеңбер ауданы", "Тіктөртбұрыш периметрі", "Тікбұрышты параллелепипед көлемі"], "Әр формуланы дұрыс атаумен сәйкестендіріңіз.", "Математика"),
        ],
        "Физика": [
            _q_single("Ньютонның екінші заңы қалай жазылады?", ["F = ma", "E = mc²", "P = mv", "V = IR"], 0, "F = ma", "Физика"),
            _q_single("Жарық вакуумдағы жылдамдығы шамамен қандай?", ["3×10⁸ м/с", "3×10⁶ м/с", "330 м/с", "1500 м/с"], 0, "c ≈ 3×10⁸ м/с", "Физика"),
            _q_multi("Қай шамалар векторлық? (Көп жауапты сұрақ)", ["Жылдамдық", "Масса", "Күш", "Температура"], [0, 2], "Жылдамдық пен күш — векторлар.", "Физика"),
            _q_match("Сәйкестендіру тесті: шама және бірлік", ["Күш", "Қуат", "Кернеу", "Жиілік"], ["Ньютон (Н)", "Ватт (Вт)", "Вольт (В)", "Герц (Гц)"], "SI бірліктерін сәйкестендіріңіз.", "Физика"),
        ],
        "Информатика": [
            _q_single("10 санының екілік жүйедегі мәні қандай?", ["1010", "1001", "1100", "1110"], 0, "8+2 = 10 → 1010₂", "Информатика"),
            _q_single("HTTP 404 коды нені білдіреді?", ["OK", "Бет табылмады", "Сервер қатесі", "Қайта бағыттау"], 1, "404 Not Found", "Информатика"),
            _q_single("Python-да тізімнің бірінші элементінің индексі қандай?", ["1", "0", "-1", "2"], 1, "Индексация 0-ден басталады.", "Информатика"),
            _q_multi("Қайлары программалау тілдері? (Көп жауапты сұрақ)", ["Python", "HTML", "Java", "CSS"], [0, 2], "HTML мен CSS — белгілеу/стиль тілдері.", "Информатика"),
            _q_match("Сәйкестендіру тесті: ұғым және анықтама", ["Алгоритм", "Дерекқор", "ОЖ", "Бит"], ["Қадамдар тізбегі", "Құрылымдалған деректер қоймасы", "Компьютерді басқару жүйесі", "Ақпараттың ең кіші бірлігі"], "Информатика терминдерін сәйкестендіріңіз.", "Информатика"),
            _q_single("RAM қандай жады?", ["Тұрақты", "Жедел (уақытша)", "Тек оқу", "Оптикалық"], 1, "RAM — жедел жады, қуат өшкенде тазартылады.", "Информатика"),
        ],
        "Химия": [
            _q_single("Су молекуласының формуласы қандай?", ["CO₂", "H₂O", "NaCl", "O₂"], 1, "H₂O", "Химия"),
            _q_single("Алтынның химиялық символы?", ["Ag", "Au", "Al", "Fe"], 1, "Au — aurum", "Химия"),
        ],
        "Биология": [
            _q_single("Фотосинтез қайда жүреді?", ["Митохондрияда", "Хлоропластта", "Ядрода", "Рибосомада"], 1, "Хлоропластта", "Биология"),
            _q_single("DNA-да аденин немен жұптасады?", ["Гуанин", "Цитозин", "Тимин", "Урацил"], 2, "A–T", "Биология"),
        ],
        "Тарих": [
            _q_single("Қазақстан тәуелсіздігін қашан жариялады?", ["16 желтоқсан 1991 ж.", "25 қазан 1990 ж.", "1 мамыр 1992 ж.", "30 тамыз 1995 ж."], 0, "16 желтоқсан 1991", "Тарих"),
            _q_match("Сәйкестендіру тесті: оқиға және жыл", ["Тәуелсіздік", "Конституция", "Астана көшірілуі", "ЭКСПО"], ["1991", "1995", "1997", "2017"], "Қазақстан тарихының негізгі даталары.", "Тарих"),
        ],
        "География": [
            _q_single("Қазақстанның астанасы қай қала?", ["Алматы", "Астана", "Шымкент", "Қарағанды"], 1, "Астана", "География"),
            _q_single("Жер шарында қанша материк бар?", ["5", "6", "7", "8"], 2, "7 материк", "География"),
        ],
        "Ағылшын тілі": [
            _q_single("Choose the correct form: She ___ to school every day.", ["go", "goes", "going", "gone"], 1, "3rd person singular: goes", "Ағылшын тілі"),
            _q_single("Антоним of 'hot' is:", ["warm", "cold", "heat", "fire"], 1, "cold", "Ағылшын тілі"),
        ],
        "Қазақ тілі мен әдебиеті": [
            _q_single("«Абай жолы» романының авторы кім?", ["Мұхтар Әуезов", "Ілияс Жансүгіров", "Сәкен Сейфуллин", "Бейімбет Майлин"], 0, "М. Әуезов", "Қазақ тілі мен әдебиеті"),
        ],
        "Орыс тілі мен әдебиеті": [
            _q_single("Автор романа «Война и мир»?", ["Чехов", "Толстой", "Достоевский", "Тургенев"], 1, "Л. Н. Толстой", "Орыс тілі мен әдебиеті"),
        ],
        "Дүниежүзі тарихы": [
            _q_single("Екінші дүниежүзілік соғыс қай жылы аяқталды?", ["1941", "1943", "1945", "1947"], 2, "1945", "Дүниежүзі тарихы"),
        ],
        "Адам. Қоғам. Құқық": [
            _q_single("ҚР жоғары заңы қалай аталады?", ["Жарлық", "Конституция", "Кодекс", "Қауға"], 1, "Конституция", "Адам. Қоғам. Құқық"),
        ],
        "Шет тілі": [
            _q_single("English: the plural of 'child' is:", ["childs", "children", "childes", "child"], 1, "children", "Шет тілі"),
        ],
    }


def build_official_quiz(subject_pair: str) -> Quiz:
    bank = question_bank()
    pair = subject_pair or "Математика - Физика"
    parts = [p.strip() for p in pair.replace("—", "-").split("-") if p.strip()]
    questions: list[Question] = []
    seen: set[str] = set()
    for subj in parts:
        for q in bank.get(subj, []):
            if q.text not in seen:
                seen.add(q.text)
                questions.append(q)
    extras = ["Математика", "Тарих", "Информатика"]
    for subj in extras:
        if len(questions) >= 12:
            break
        for q in bank.get(subj, []):
            if q.text not in seen:
                seen.add(q.text)
                questions.append(q)
                if len(questions) >= 12:
                    break
    if not questions:
        questions = bank["Математика"][:]
    return Quiz(
        id=f"official_{int(time.time())}",
        title="ҰБТ Үлгілік Тест",
        description=f"НЦТ ережелеріне сәйкес үлгілік сессия · {pair}",
        author="НЦТ",
        questions=questions,
        subject_pair=pair,
        is_official=True,
        duration_minutes=DEFAULT_TEST_MINUTES,
    )


class QuizRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._quizzes: dict[str, Quiz] = {}
        self.load()

    def load(self) -> None:
        self._quizzes.clear()
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                for item in raw:
                    quiz = Quiz.from_dict(item)
                    if not quiz.is_official:
                        self._quizzes[quiz.id] = quiz
            except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
                pass

    def save(self) -> None:
        payload = [q.to_dict() for q in self._quizzes.values() if not q.is_official]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_user_quizzes(self) -> list[Quiz]:
        return sorted(self._quizzes.values(), key=lambda q: q.created_at, reverse=True)

    def upsert(self, quiz: Quiz) -> None:
        self._quizzes[quiz.id] = quiz
        self.save()

    def delete(self, quiz_id: str) -> bool:
        quiz = self._quizzes.get(quiz_id)
        if quiz is None or quiz.is_official:
            return False
        del self._quizzes[quiz_id]
        self.save()
        return True


# ---------------------------------------------------------------------------
# Dialog helpers
# ---------------------------------------------------------------------------
def open_dialog(page: ft.Page, dialog: ft.AlertDialog) -> None:
    try:
        page.open(dialog)
        page.update()
        return
    except Exception:
        pass
    try:
        page.dialog = dialog
        dialog.open = True
    except Exception:
        if dialog not in page.overlay:
            page.overlay.append(dialog)
        dialog.open = True
    page.update()


def close_dialog(page: ft.Page, dialog: Optional[ft.AlertDialog] = None) -> None:
    if dialog is not None:
        try:
            page.close(dialog)
            page.update()
            return
        except Exception:
            dialog.open = False
    page.update()


def show_snack(page: ft.Page, message: str, *, error: bool = False) -> None:
    bar = ft.SnackBar(
        content=ft.Text(message, color="#f8fafc"),
        bgcolor=P.red if error else P.green,
        duration=3200,
    )
    try:
        page.open(bar)
        return
    except Exception:
        pass
    page.snack_bar = bar
    bar.open = True
    page.update()


def dropdown_option(label: str, key: Optional[str] = None):
    k = key if key is not None else label
    if hasattr(ft, "dropdown") and hasattr(ft.dropdown, "Option"):
        try:
            return ft.dropdown.Option(key=k, text=label)
        except TypeError:
            return ft.dropdown.Option(label)
    if hasattr(ft, "DropdownOption"):
        return ft.DropdownOption(key=k, text=label)
    return ft.dropdown.Option(label)


def field(
    label: str,
    *,
    value: str = "",
    multiline: bool = False,
    password: bool = False,
    min_lines: int = 1,
    max_lines: int = 1,
    accent: Optional[str] = None,
) -> ft.TextField:
    color = accent or P.accent
    return ft.TextField(
        label=label,
        value=value,
        multiline=multiline,
        min_lines=min_lines,
        max_lines=max_lines,
        password=password,
        can_reveal_password=password,
        border_radius=8,
        border_color=P.border,
        focused_border_color=color,
        color=P.text,
        label_style=ft.TextStyle(color=P.muted),
        cursor_color=color,
        bgcolor=P.card,
    )


def make_card(
    content: ft.Control,
    *,
    padding: int = 16,
    bgcolor: Optional[str] = None,
    on_click: Optional[Callable] = None,
) -> ft.Container:
    return ft.Container(
        content=content,
        padding=padding,
        bgcolor=bgcolor or P.card,
        border_radius=8,
        border=ft.border.all(1, P.border),
        on_click=on_click,
        ink=bool(on_click),
    )


def title_text(text: str, size: int = 22) -> ft.Text:
    return ft.Text(text, size=size, weight=ft.FontWeight.BOLD, color=P.text)


def muted(text: str, size: int = 13) -> ft.Text:
    return ft.Text(text, size=size, color=P.muted)


def primary_button(
    text: str,
    on_click: Callable,
    *,
    disabled: bool = False,
    icon=None,
    bgcolor: Optional[str] = None,
    expand: bool = False,
) -> ft.ElevatedButton:
    kwargs: dict[str, Any] = {
        "text": text,
        "on_click": on_click,
        "disabled": disabled,
        "bgcolor": bgcolor or P.accent,
        "color": "#f8fafc",
        "style": ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
        ),
    }
    if icon is not None:
        kwargs["icon"] = icon
    if expand:
        kwargs["expand"] = True
    return ft.ElevatedButton(**kwargs)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def fmt_mmss(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def practice_banner() -> ft.Container:
    return ft.Container(
        content=ft.Text(
            PRACTICE_DISCLAIMER,
            color="#431407",
            size=13,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        ),
        bgcolor="#fde68a",
        padding=12,
        border_radius=8,
        border=ft.border.all(2, "#d97706"),
        alignment=ft.alignment.center,
    )


def subject_of(q: Question) -> str:
    return (q.subject or "").strip() or "Жалпы"


def grade_question(q: Question, ans: Any) -> tuple[bool, int]:
    if ans is None or ans == "" or ans == []:
        return False, 0
    if q.qtype == QTYPE_MATCH and q.match_left:
        if not isinstance(ans, list):
            return False, 0
        total_p = len(q.match_right) or 1
        ok_n = sum(1 for i, s in enumerate(ans) if i < len(q.match_right) and s == q.match_right[i])
        earned = int(POINTS_BASE * (ok_n / total_p))
        return ok_n == len(q.match_right), earned
    if q.qtype == QTYPE_MULTI:
        correct = {i for i, c in enumerate(q.choices) if c.is_correct}
        picked = set(ans) if isinstance(ans, list) else set()
        ok = picked == correct
        return ok, POINTS_BASE if ok else 0
    correct_idx = next((i for i, c in enumerate(q.choices) if c.is_correct), -1)
    ok = ans == correct_idx
    return ok, POINTS_BASE if ok else 0


def correct_answer_text(q: Question) -> str:
    if q.qtype == QTYPE_MATCH:
        return " | ".join(f"{a} → {b}" for a, b in zip(q.match_left, q.match_right))
    if q.qtype == QTYPE_MULTI:
        return ", ".join(c.text for c in q.choices if c.is_correct)
    for c in q.choices:
        if c.is_correct:
            return c.text
    return "—"


def step_explanation(q: Question) -> str:
    if q.qtype == QTYPE_SINGLE:
        step1 = "1-қадам: Сұрақтың шартын оқып, бір ғана дұрыс нұсқаны таңдаңыз."
    elif q.qtype == QTYPE_MULTI:
        step1 = "1-қадам: Бұл көп жауапты сұрақ — барлық дұрыс нұсқаларды белгілеу керек."
    else:
        step1 = "1-қадам: A бағанның әр жолын B бағандағы сәйкес ұғыммен байланыстырыңыз."
    step2 = f"2-қадам: Дұрыс жауап — {correct_answer_text(q)}."
    step3 = f"3-қадам: {q.explanation}" if q.explanation else "3-қадам: Жауапты пән теориясымен салыстырыңыз."
    return f"{step1}\n{step2}\n{step3}"


def safe_calc(expr: str) -> str:
    raw = (expr or "").strip().replace("×", "*").replace("÷", "/").replace(",", ".")
    raw = raw.replace("%", "/100")
    if not raw:
        return ""
    if not re.fullmatch(r"[0-9+\-*/().\s]+", raw):
        return "Қате өрнек"
    try:
        val = eval(raw, {"__builtins__": {}}, {})
        if isinstance(val, float):
            if val.is_integer():
                return str(int(val))
            return str(round(val, 10)).rstrip("0").rstrip(".")
        return str(val)
    except Exception:
        return "Қате"


PERIODIC_ELEMENTS: list[tuple[int, str, str, str]] = [
    (1, "H", "Сутегі", "1.008"), (2, "He", "Гелий", "4.003"),
    (3, "Li", "Литий", "6.94"), (4, "Be", "Бериллий", "9.012"),
    (5, "B", "Бор", "10.81"), (6, "C", "Көміртегі", "12.01"),
    (7, "N", "Азот", "14.01"), (8, "O", "Оттегі", "16.00"),
    (9, "F", "Фтор", "19.00"), (10, "Ne", "Неон", "20.18"),
    (11, "Na", "Натрий", "22.99"), (12, "Mg", "Магний", "24.31"),
    (13, "Al", "Алюминий", "26.98"), (14, "Si", "Кремний", "28.09"),
    (15, "P", "Фосфор", "30.97"), (16, "S", "Күкірт", "32.06"),
    (17, "Cl", "Хлор", "35.45"), (18, "Ar", "Аргон", "39.95"),
    (19, "K", "Калий", "39.10"), (20, "Ca", "Кальций", "40.08"),
    (21, "Sc", "Скандий", "44.96"), (22, "Ti", "Титан", "47.87"),
    (23, "V", "Ванадий", "50.94"), (24, "Cr", "Хром", "52.00"),
    (25, "Mn", "Марганец", "54.94"), (26, "Fe", "Темір", "55.85"),
    (27, "Co", "Кобальт", "58.93"), (28, "Ni", "Никель", "58.69"),
    (29, "Cu", "Мыс", "63.55"), (30, "Zn", "Мырыш", "65.38"),
    (31, "Ga", "Галлий", "69.72"), (32, "Ge", "Германий", "72.63"),
    (33, "As", "Мышьяк", "74.92"), (34, "Se", "Селен", "78.97"),
    (35, "Br", "Бром", "79.90"), (36, "Kr", "Криптон", "83.80"),
    (37, "Rb", "Рубидий", "85.47"), (38, "Sr", "Стронций", "87.62"),
    (39, "Y", "Иттрий", "88.91"), (40, "Zr", "Цирконий", "91.22"),
    (47, "Ag", "Күміс", "107.87"), (48, "Cd", "Кадмий", "112.41"),
    (50, "Sn", "Қалайы", "118.71"), (53, "I", "Йод", "126.90"),
    (54, "Xe", "Ксенон", "131.29"), (55, "Cs", "Цезий", "132.91"),
    (56, "Ba", "Барий", "137.33"), (74, "W", "Вольфрам", "183.84"),
    (78, "Pt", "Платина", "195.08"), (79, "Au", "Алтын", "196.97"),
    (80, "Hg", "Сынап", "200.59"), (82, "Pb", "Қорғасын", "207.2"),
    (92, "U", "Уран", "238.03"),
]


# ---------------------------------------------------------------------------
# Application Class
# ---------------------------------------------------------------------------
class UBTApp:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.repo = QuizRepository(_path(QUIZZES_FILE))
        self.users: dict[str, Any] = {}
        self.current_email = ""
        self.teacher_authenticated = False
        self.active_quiz: Optional[Quiz] = None
        self.selected_pair = "Математика - Информатика"
        self.test_answers: list[Any] = []
        self.test_index = 0
        self.test_score = 0
        self.test_correct_count = 0
        self.timer_remaining = DEFAULT_TEST_MINUTES * 60
        self.timer_running = False
        self._timer_id = 0
        self.timer_label: Optional[ft.Text] = None
        self.answered_this_question = False
        self.match_orders: dict[int, list[str]] = {}
        self._shell_bg: Optional[ft.Container] = None

        self._load_settings()
        self._load_users()
        self._configure_page()

        self.header = ft.Container(padding=0)
        self.body = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=0)
        self._shell_bg = ft.Container(
            content=self.body,
            expand=True,
            padding=ft.padding.symmetric(horizontal=14, vertical=10),
            bgcolor=P.bg,
        )
        shell = ft.Column([self.header, self._shell_bg], expand=True, spacing=0)
        page.controls.clear()
        try:
            page.add(ft.SafeArea(content=shell, expand=True))
        except Exception:
            page.add(shell)

        if self.current_email and self.current_email in self.users:
            self.show_home()
        else:
            self.show_auth()

    # persistence ----------------------------------------------------------
    def _load_settings(self) -> None:
        path = _path(SETTINGS_FILE)
        theme_key = "slate"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                theme_key = str(data.get("theme", "slate"))
            except (json.JSONDecodeError, OSError):
                pass
        P.apply(theme_key)

    def _save_settings(self) -> None:
        path = _path(SETTINGS_FILE)
        path.write_text(json.dumps({"theme": P.key}, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_users(self) -> None:
        path = _path(USERS_FILE)
        self.users = {}
        self.current_email = ""
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.users = data.get("users", {}) or {}
            email = str(data.get("current_email", "")).strip().lower()
            if email in self.users:
                self.current_email = email
        except (json.JSONDecodeError, OSError, TypeError):
            self.users = {}

    def _save_users(self) -> None:
        path = _path(USERS_FILE)
        path.write_text(
            json.dumps(
                {"users": self.users, "current_email": self.current_email},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _current_user(self) -> Optional[dict[str, Any]]:
        return self.users.get(self.current_email)

    def _record_result(self, quiz: Quiz, correct: int, total: int, score: int, percent: int) -> None:
        user = self._current_user()
        if user is None:
            return
        stats = user.setdefault(
            "stats",
            {
                "tests_taken": 0,
                "total_correct": 0,
                "total_questions": 0,
                "best_percent": 0,
                "history": [],
            },
        )
        stats["tests_taken"] = int(stats.get("tests_taken", 0)) + 1
        stats["total_correct"] = int(stats.get("total_correct", 0)) + correct
        stats["total_questions"] = int(stats.get("total_questions", 0)) + total
        stats["best_percent"] = max(int(stats.get("best_percent", 0)), percent)
        history = list(stats.get("history") or [])
        history.insert(
            0,
            {
                "quiz": quiz.title,
                "pair": quiz.subject_pair,
                "score": score,
                "correct": correct,
                "total": total,
                "percent": percent,
                "at": time.time(),
            },
        )
        stats["history"] = history[:30]
        self._save_users()

    # page chrome ----------------------------------------------------------
    def _configure_page(self) -> None:
        p = self.page
        p.title = "ҰБТ / ЕНТ Quiz App"
        p.theme_mode = ft.ThemeMode.LIGHT if P.key == "light" else ft.ThemeMode.DARK
        p.bgcolor = P.bg
        p.padding = 0
        p.theme = ft.Theme(color_scheme_seed=P.accent)

    def _apply_theme(self, key: str) -> None:
        P.apply(key)
        self._save_settings()
        self._configure_page()
        if self._shell_bg is not None:
            self._shell_bg.bgcolor = P.bg
        if self.current_email:
            self.show_settings()
        else:
            self.show_auth()

    def _set_header(self, title: str, *, show_back: bool = True, test_mode: bool = False) -> None:
        def go_back(_: Any = None) -> None:
            if test_mode and self.active_quiz is not None:
                self._confirm_exit_test()
                return
            if self.current_email:
                self.show_home()
            else:
                self.show_auth()

        leading = (
            ft.IconButton(
                icon=_icon("ARROW_BACK", "arrow_back"),
                icon_color=P.text,
                on_click=go_back,
            )
            if show_back
            else ft.Container(width=40)
        )
        tools: list[ft.Control] = []
        if test_mode:
            tools = [
                ft.IconButton(
                    icon=_icon("CALCULATE", "calculate"),
                    icon_color=P.accent,
                    tooltip="Калькулятор",
                    on_click=lambda _: self.open_calculator(),
                ),
                ft.IconButton(
                    icon=_icon("SCIENCE", "science"),
                    icon_color=P.purple,
                    tooltip="Менделеев кестесі",
                    on_click=lambda _: self.open_periodic_table(),
                ),
            ]
        self.header.content = ft.Container(
            content=ft.Row(
                [
                    leading,
                    ft.Text(title, color=P.text, weight=ft.FontWeight.W_600, size=16, expand=True),
                    *tools,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=P.card,
            padding=ft.padding.symmetric(horizontal=6, vertical=6),
        )

    def show_screen(self, title: str, content: ft.Control, *, show_back: bool = True) -> None:
        test_mode = title == "Тест сессиясы"
        if not test_mode:
            self.timer_running = False
        self._set_header(title, show_back=show_back, test_mode=test_mode)
        self.body.controls = [content]
        if self._shell_bg is not None:
            self._shell_bg.bgcolor = P.bg
        self.page.bgcolor = P.bg
        self.page.update()

    def _alert(self, title: str, message: str) -> None:
        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=P.card,
            title=ft.Text(title, color=P.text, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Text(message, color=P.muted),
                width=320,
            ),
            actions=[],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=8),
        )
        dialog.actions = [
            ft.TextButton(
                "Жабу",
                on_click=lambda _: close_dialog(self.page, dialog),
                style=ft.ButtonStyle(color=P.accent),
            )
        ]
        open_dialog(self.page, dialog)

    # Auth -----------------------------------------------------------------
    def show_auth(self) -> None:
        self.timer_running = False
        mode = {"v": "login"}
        name_f = field("Аты-жөні")
        email_f = field("Email")
        pass_f = field("Құпия сөз", password=True)
        hint = ft.Text("Аккаунтқа кіріңіз", color=P.muted, size=13)
        toggle_btn = ft.TextButton("Тіркелгі жоқ па? Тіркелу")

        def set_mode(login: bool) -> None:
            mode["v"] = "login" if login else "register"
            name_f.visible = not login
            hint.value = "Аккаунтқа кіріңіз" if login else "Жаңа оқушы аккаунтын құрыңыз"
            action_btn.text = "Кіру" if login else "Тіркелу"
            toggle_btn.text = "Тіркелгі жоқ па? Тіркелу" if login else "Аккаунт бар ма? Кіру"
            self.page.update()

        def submit(_: Any = None) -> None:
            email = (email_f.value or "").strip().lower()
            password = (pass_f.value or "").strip()
            name = (name_f.value or "").strip()
            if not email or "@" not in email:
                show_snack(self.page, "Email дұрыс емес", error=True)
                return
            if len(password) < 4:
                show_snack(self.page, "Құпия сөз кемінде 4 таңба", error=True)
                return
            if contains_bad_words(name) or contains_bad_words(email):
                self._alert("Ескерту", PROFANITY_MSG)
                return
            if mode["v"] == "register":
                if not name:
                    show_snack(self.page, "Аты-жөніңізді енгізіңіз", error=True)
                    return
                if email in self.users:
                    show_snack(self.page, "Бұл email тіркелген", error=True)
                    return
                self.users[email] = {
                    "name": name,
                    "email": email,
                    "password": hash_password(password),
                    "created_at": time.time(),
                    "stats": {
                        "tests_taken": 0,
                        "total_correct": 0,
                        "total_questions": 0,
                        "best_percent": 0,
                        "history": [],
                    },
                }
                self.current_email = email
                self._save_users()
                show_snack(self.page, "Тіркелу сәтті ✓")
                self.show_home()
                return
            user = self.users.get(email)
            if not user or user.get("password") != hash_password(password):
                show_snack(self.page, "Email немесе құпия сөз қате", error=True)
                return
            self.current_email = email
            self._save_users()
            show_snack(self.page, f"Қош келдіңіз, {user.get('name', '')}!")
            self.show_home()

        action_btn = primary_button("Кіру", submit, expand=True, icon=_icon("LOGIN", "login"))
        toggle_btn.on_click = lambda _: set_mode(mode["v"] != "login")
        email_f.on_submit = submit
        pass_f.on_submit = submit
        name_f.visible = False

        content = ft.Column(
            [
                ft.Container(height=12),
                ft.Column(
                    [
                        ft.Text("ҰБТ / ЕНТ", size=32, weight=ft.FontWeight.BOLD, color=P.text),
                        ft.Text("Оқушы аккаунты", size=14, color=P.accent, weight=ft.FontWeight.W_500),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                ),
                make_card(
                    ft.Column(
                        [hint, name_f, email_f, pass_f, action_btn, toggle_btn],
                        spacing=10,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    )
                ),
                muted("Прогресс, ұпайлар және статистика құрылғыда сақталады."),
            ],
            spacing=14,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self.show_screen("Кіру", content, show_back=False)

    def logout(self) -> None:
        self.current_email = ""
        self.teacher_authenticated = False
        self._save_users()
        self.show_auth()

    # Home -----------------------------------------------------------------
    def show_home(self) -> None:
        self.timer_running = False
        self.active_quiz = None
        user = self._current_user() or {}
        name = user.get("name") or "Оқушы"
        stats = user.get("stats") or {}
        taken = int(stats.get("tests_taken", 0))
        best = int(stats.get("best_percent", 0))

        def card(title: str, subtitle: str, accent: str, handler: Callable) -> ft.Container:
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Text(title, size=17, weight=ft.FontWeight.BOLD, color=P.text),
                        ft.Text(subtitle, size=12, color=P.muted),
                    ],
                    spacing=6,
                    tight=True,
                ),
                padding=18,
                bgcolor=P.card,
                border_radius=8,
                border=ft.border.only(left=ft.BorderSide(4, accent)),
                on_click=lambda _: handler(),
                ink=True,
            )

        content = ft.Column(
            [
                ft.Container(height=6),
                ft.Column(
                    [
                        ft.Text("ҰБТ / ЕНТ", size=30, weight=ft.FontWeight.BOLD, color=P.text),
                        ft.Text(f"Сәлем, {name}", size=14, color=P.accent, weight=ft.FontWeight.W_500),
                        muted("Ұлттық тестілеу орталығы стиліндегі квиз қосымшасы"),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                ),
                ft.Row(
                    [
                        make_card(
                            ft.Column(
                                [ft.Text(str(taken), size=20, weight=ft.FontWeight.BOLD, color=P.accent), muted("Тест")],
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=2,
                                tight=True,
                            ),
                            padding=12,
                        ),
                        make_card(
                            ft.Column(
                                [ft.Text(f"{best}%", size=20, weight=ft.FontWeight.BOLD, color=P.green), muted("Үздік")],
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=2,
                                tight=True,
                            ),
                            padding=12,
                        ),
                    ],
                    spacing=10,
                ),
                card("🏛️  ҰБТ / ЕНТ Тест", "НЦТ ережелері, бейіндік пәндер және үлгілік тест", P.accent, self.show_ntc_rules),
                card("🎮  Пайдаланушылар Квиздері", "Мұғалім / оқушы құрған квиздер", P.purple, self.show_user_quizzes),
                card("✏️  Тест құрастыру (Оқушы)", "Жеңілдетілген квиз редакторы", P.green, lambda: self.show_creator(False)),
                card("🔒  Мұғалім Бөлімі", "Құпия сөзбен қорғалған басқару панелі", P.amber, self.open_teacher_auth),
                card("👤  Менің статистикам", "Соңғы нәтижелер және прогресс", P.purple, self.show_stats),
                card("🎨  Тақырып / тұсқағаз", "Фон түсі мен стильді таңдау", P.accent, self.show_settings),
                ft.TextButton("Шығу", on_click=lambda _: self.logout(), style=ft.ButtonStyle(color=P.red)),
                muted(f"Сақталған квиздер: {len(self.repo.list_user_quizzes())}"),
                ft.Container(height=16),
            ],
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self.show_screen("ҰБТ / ЕНТ", content, show_back=False)

    def show_stats(self) -> None:
        user = self._current_user() or {}
        stats = user.get("stats") or {}
        history = list(stats.get("history") or [])
        items: list[ft.Control] = [
            title_text(user.get("name") or "Оқушы", 20),
            muted(user.get("email") or ""),
            muted(
                f"Тесттер: {stats.get('tests_taken', 0)} · "
                f"Дұрыс: {stats.get('total_correct', 0)}/{stats.get('total_questions', 0)} · "
                f"Үздік: {stats.get('best_percent', 0)}%"
            ),
            ft.Divider(color=P.border),
            title_text("Соңғы нәтижелер", 16),
        ]
        if not history:
            items.append(muted("Әзірге нәтиже жоқ. Тест тапсырыңыз."))
        else:
            for item in history[:12]:
                ts = time.strftime("%d.%m.%Y %H:%M", time.localtime(float(item.get("at", time.time()))))
                items.append(
                    make_card(
                        ft.Column(
                            [
                                ft.Text(str(item.get("quiz", "")), color=P.text, weight=ft.FontWeight.W_600, size=14),
                                muted(
                                    f"{item.get('percent', 0)}% · {item.get('correct', 0)}/{item.get('total', 0)} · "
                                    f"{item.get('score', 0)} ұпай · {ts}"
                                ),
                            ],
                            spacing=4,
                        ),
                        padding=12,
                    )
                )
        items.append(ft.Container(height=20))
        self.show_screen("Статистика", ft.Column(items, spacing=10))

    def show_settings(self) -> None:
        tiles: list[ft.Control] = [
            title_text("Тақырып / тұсқағаз", 20),
            muted("Қосымшаның фон түсін таңдаңыз. Таңдау құрылғыда сақталады."),
        ]
        for key, meta in THEMES.items():
            selected = key == P.key
            tiles.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(width=28, height=28, bgcolor=meta["bg"], border_radius=8, border=ft.border.all(2, meta["accent"])),
                            ft.Column(
                                [
                                    ft.Text(meta["name"], color=P.text, weight=ft.FontWeight.W_600),
                                    ft.Text(key, size=11, color=P.muted),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Text("✓" if selected else "", color=P.green, size=18),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=14,
                    bgcolor=P.card,
                    border_radius=8,
                    border=ft.border.all(2, P.accent if selected else P.border),
                    on_click=lambda e, k=key: self._apply_theme(k),
                    ink=True,
                )
            )
        tiles.append(ft.Container(height=20))
        self.show_screen("Параметрлер", ft.Column(tiles, spacing=10))

    # NTC + Profile selection ----------------------------------------------
    def show_ntc_rules(self) -> None:
        start_btn = primary_button(
            "Тестілеуді бастау",
            lambda _: None,
            disabled=True,
            icon=_icon("PLAY_ARROW", "play_arrow"),
            bgcolor=P.card_alt,
            expand=True,
        )
        agree = ft.Checkbox(
            label="Мен НЦТ тестілеу ережелерімен таныстым және келісемін",
            value=False,
            fill_color=P.accent,
            check_color="#f8fafc",
            label_style=ft.TextStyle(color=P.text, size=13),
        )

        def apply_agree_state(agreed: bool) -> None:
            start_btn.disabled = not agreed
            start_btn.bgcolor = P.accent if agreed else P.card_alt
            start_btn.on_click = (lambda _: self.show_profile_select()) if agreed else (lambda _: None)
            try:
                start_btn.update()
            except Exception:
                self.page.update()

        agree.on_change = lambda e: apply_agree_state(bool(getattr(e.control, "value", False)))

        rules = [
            "Тестілеуші жеке басын куәландыратын құжатпен келуі тиіс.",
            "ҰБТ ұзақтығы — 4 сағат (240 минут, бейіндік пәндермен).",
            "Әр тестіленушіге жеке компьютер / құрылғы бөлінеді.",
            "Тест кезінде сөйлесу, көшіру және бөгде материалдар тыйым салынады.",
            "Ұялы телефон және смарт-құрылғылар өткізу пунктіне жіберілмейді.",
            "Дұрыс жауаптар үшін ұпай беріледі; қате жауап ұпай алмайды.",
            "Техникалық ақау кезінде прокторға дереу хабарлау қажет.",
            "Ережені бұзған жағдайда нәтиже жойылуы мүмкін.",
            "Нәтижелер ресми порталда жарияланады.",
            "Апелляция белгіленген мерзімде беріледі.",
        ]
        pair_rows: list[ft.Control] = []
        for code, s1, s2 in SUBJECT_PAIRS:
            pair_rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(code, color=P.accent, width=36, weight=ft.FontWeight.BOLD, size=12),
                            ft.Text(f"{s1}  —  {s2}", color=P.text, size=12, expand=True),
                        ]
                    ),
                    padding=ft.padding.symmetric(vertical=6, horizontal=8),
                    bgcolor=P.card_alt,
                    border_radius=6,
                )
            )

        content = ft.Column(
            [
                make_card(
                    ft.Column(
                        [
                            title_text("НЦТ ережелері", 20),
                            muted("Ұлттық тестілеу орталығы — ресми талаптар"),
                            ft.Divider(color=P.border, height=16),
                            ft.Column([ft.Text(f"{i + 1}. {r}", color=P.text, size=13) for i, r in enumerate(rules)], spacing=8),
                        ],
                        spacing=8,
                    )
                ),
                make_card(
                    ft.Column(
                        [
                            title_text("Бейіндік пәндер комбинациясы", 16),
                            muted("Информатика қоса алғанда рұқсат етілген жұптар"),
                            ft.Column(pair_rows, spacing=6),
                        ],
                        spacing=8,
                    )
                ),
                make_card(ft.Column([agree, ft.Container(height=6), start_btn], spacing=4)),
                ft.Container(height=20),
            ],
            spacing=14,
        )
        self.show_screen("НЦТ ережелері", content)

    def show_profile_select(self) -> None:
        pair_labels = [f"{s1} - {s2}" for _, s1, s2 in SUBJECT_PAIRS]
        if self.selected_pair not in pair_labels:
            self.selected_pair = "Математика - Информатика"
            if self.selected_pair not in pair_labels:
                self.selected_pair = pair_labels[0]

        dd = ft.Dropdown(
            label="Бейіндік пәндер жұбы",
            options=[dropdown_option(p) for p in pair_labels],
            value=self.selected_pair,
            border_radius=8,
            border_color=P.border,
            focused_border_color=P.accent,
            color=P.text,
            label_style=ft.TextStyle(color=P.muted),
            bgcolor=P.card,
        )
        subj1 = ft.Dropdown(
            label="1-бейіндік пән",
            options=[dropdown_option(s) for s in ELECTIVE_SUBJECTS],
            value="Математика",
            border_radius=8,
            border_color=P.border,
            focused_border_color=P.accent,
            color=P.text,
            label_style=ft.TextStyle(color=P.muted),
            bgcolor=P.card,
        )
        subj2 = ft.Dropdown(
            label="2-бейіндік пән",
            options=[dropdown_option(s) for s in ELECTIVE_SUBJECTS],
            value="Информатика",
            border_radius=8,
            border_color=P.border,
            focused_border_color=P.purple,
            color=P.text,
            label_style=ft.TextStyle(color=P.muted),
            bgcolor=P.card,
        )

        def sync_from_pair(e: Any = None) -> None:
            val = str(dd.value or self.selected_pair)
            parts = [p.strip() for p in val.split(" - ")]
            if len(parts) == 2:
                if parts[0] in ELECTIVE_SUBJECTS:
                    subj1.value = parts[0]
                if parts[1] in ELECTIVE_SUBJECTS:
                    subj2.value = parts[1]
            self.page.update()

        def sync_from_subjects(_: Any = None) -> None:
            a = str(subj1.value or "")
            b = str(subj2.value or "")
            combo = f"{a} - {b}"
            if a and b and a != b:
                dd.value = combo if combo in pair_labels else dd.value
                self.page.update()

        dd.on_change = sync_from_pair
        subj1.on_change = sync_from_subjects
        subj2.on_change = sync_from_subjects

        def confirm(_: Any = None) -> None:
            a = str(subj1.value or "").strip()
            b = str(subj2.value or "").strip()
            if not a or not b:
                show_snack(self.page, "Екі пәнді де таңдаңыз", error=True)
                return
            if a == b:
                show_snack(self.page, "Пәндер әртүрлі болуы керек", error=True)
                return
            pair = f"{a} - {b}"
            official = [f"{s1} - {s2}" for _, s1, s2 in SUBJECT_PAIRS]
            if pair not in official and f"{b} - {a}" in official:
                pair = f"{b} - {a}"
            self.selected_pair = pair
            self.start_official_test()

        content = ft.Column(
            [
                make_card(
                    ft.Column(
                        [
                            title_text("Бейіндік пәндерді таңдау", 18),
                            muted("Информатика, математика, физика және басқа пәндерді таңдап растаңыз."),
                            dd,
                            subj1,
                            subj2,
                            muted("Міндетті блок: Қазақстан тарихы, математикалық / оқу сауаттылығы үлгісі қосылады."),
                            primary_button(
                                "Растау және тестті бастау",
                                confirm,
                                icon=_icon("CHECK", "check"),
                                expand=True,
                            ),
                        ],
                        spacing=12,
                    )
                ),
                ft.Container(height=20),
            ],
            spacing=12,
        )
        self.show_screen("Пән таңдау", content)

    def start_official_test(self) -> None:
        quiz = build_official_quiz(self.selected_pair)
        self.launch_test(quiz)

    # User Quizzes ---------------------------------------------------------
    def show_user_quizzes(self) -> None:
        quizzes = self.repo.list_user_quizzes()
        items: list[ft.Control] = [
            title_text("Пайдаланушылар Квиздері"),
            muted("Сақталған квиздерді таңдап, тестті бастаңыз"),
            ft.Container(height=6),
        ]
        if not quizzes:
            items.append(
                make_card(
                    ft.Column(
                        [
                            title_text("Квиздер жоқ", 18),
                            muted("Оқушы немесе мұғалім бөлімінен жаңа квиз құрыңыз."),
                            primary_button("Тест құрастыру", lambda _: self.show_creator(False), icon=_icon("ADD", "add")),
                        ],
                        spacing=8,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=24,
                )
            )
        else:
            for quiz in quizzes:
                items.append(self._quiz_list_card(quiz, allow_delete=True))
        items.append(ft.Container(height=20))
        self.show_screen("Пайдаланушылар Квиздері", ft.Column(items, spacing=12))

    def _quiz_list_card(self, quiz: Quiz, *, allow_delete: bool) -> ft.Container:
        qtypes = ", ".join(sorted({q.qtype for q in quiz.questions})) or QTYPE_SINGLE
        return make_card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(quiz.title, size=16, weight=ft.FontWeight.BOLD, color=P.text),
                                    muted(
                                        f"{quiz.author} · {len(quiz.questions)} сұрақ · {quiz.duration_minutes} мин"
                                        + (f" · {quiz.subject_pair}" if quiz.subject_pair else "")
                                    ),
                                    muted(f"Түрлері: {qtypes}", 11),
                                ],
                                expand=True,
                                spacing=2,
                            ),
                            ft.ElevatedButton(
                                "Жою",
                                icon=_icon("DELETE_OUTLINE", "delete"),
                                bgcolor=P.red,
                                color="#f8fafc",
                                visible=allow_delete,
                                on_click=lambda e, q=quiz: self.confirm_delete(q),
                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                            ),
                        ]
                    ),
                    muted(quiz.description or "Сипаттама жоқ", 12),
                    primary_button(
                        "Бастау",
                        lambda e, q=quiz: self.launch_test(q),
                        icon=_icon("PLAY_ARROW", "play_arrow"),
                        bgcolor=P.purple,
                        expand=True,
                    ),
                ],
                spacing=10,
            ),
            padding=14,
        )

    def confirm_delete(self, quiz: Quiz) -> None:
        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=P.card,
            title=ft.Text("Квизді жою?", color=P.text, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Text(f"«{quiz.title}» біржола жойылады.", color=P.muted),
                width=300,
            ),
            actions=[],
            shape=ft.RoundedRectangleBorder(radius=8),
        )

        def do_delete(_: Any) -> None:
            close_dialog(self.page, dialog)
            if self.repo.delete(quiz.id):
                show_snack(self.page, f"«{quiz.title}» жойылды")
                if self.teacher_authenticated:
                    self.show_teacher_hub()
                else:
                    self.show_user_quizzes()
            else:
                show_snack(self.page, "Жою сәтсіз", error=True)

        dialog.actions = [
            ft.TextButton("Бас тарту", on_click=lambda _: close_dialog(self.page, dialog), style=ft.ButtonStyle(color=P.muted)),
            ft.TextButton("Жою", on_click=do_delete, style=ft.ButtonStyle(color=P.red)),
        ]
        open_dialog(self.page, dialog)

    # Teacher Module -------------------------------------------------------
    def open_teacher_auth(self) -> None:
        if self.teacher_authenticated:
            self.show_teacher_hub()
            return

        password_field = field("Құпия сөз", password=True, accent=P.amber)
        error_text = ft.Text("", color=P.red, size=12, visible=False)
        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=P.card,
            title=ft.Text("🔒 Мұғалім Бөлімі", color=P.text, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column(
                    [muted("Жалғастыру үшін құпия сөзді енгізіңіз"), password_field, error_text],
                    tight=True,
                    spacing=12,
                ),
                width=320,
                height=160,
            ),
            actions=[],
            shape=ft.RoundedRectangleBorder(radius=8),
        )

        def try_login(_: Any = None) -> None:
            entered = (password_field.value or "").strip()
            if entered == TEACHER_PASSWORD:
                self.teacher_authenticated = True
                close_dialog(self.page, dialog)
                show_snack(self.page, "Мұғалім бөліміне кірдіңіз ✓")
                self.show_teacher_hub()
                return
            error_text.value = "Қате құпия сөз. Қайта көріңіз."
            error_text.visible = True
            password_field.value = ""
            self.page.update()

        password_field.on_submit = try_login
        dialog.actions = [
            ft.TextButton("Бас тарту", on_click=lambda _: close_dialog(self.page, dialog), style=ft.ButtonStyle(color=P.muted)),
            ft.ElevatedButton(
                "Кіру",
                on_click=try_login,
                bgcolor=P.amber,
                color="#0f172a",
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
            ),
        ]
        open_dialog(self.page, dialog)

    def show_teacher_hub(self) -> None:
        quizzes = self.repo.list_user_quizzes()
        items: list[ft.Control] = [
            title_text("Мұғалім панелі", 20),
            muted("Квиз құру, жою және барлық сұрақ түрлерін басқару"),
            primary_button(
                "Жаңа квиз құру",
                lambda _: self.show_creator(True),
                icon=_icon("ADD", "add"),
                bgcolor=P.amber,
                expand=True,
            ),
            ft.Divider(color=P.border),
        ]
        if not quizzes:
            items.append(muted("Әзірге пайдаланушы квиздері жоқ."))
        else:
            for quiz in quizzes:
                items.append(self._quiz_list_card(quiz, allow_delete=True))
        items.append(ft.Container(height=20))
        self.show_screen("Мұғалім Бөлімі", ft.Column(items, spacing=12))

    # Creator --------------------------------------------------------------
    def show_creator(self, advanced: bool) -> None:
        heading = "Мұғалім — Тест құрастыру" if advanced else "Оқушы — Тест құрастыру"
        title_field = field("Квиз атауы")
        desc_field = field("Сипаттама", multiline=True, min_lines=2, max_lines=3)
        author_field = field("Автор", value="Мұғалім" if advanced else "Оқушы")
        minutes_field = field("Ұзақтығы (минут)", value=str(40 if advanced else 20))

        pair_labels = [f"{s1} - {s2}" for _, s1, s2 in SUBJECT_PAIRS]
        subject_dd: Optional[ft.Dropdown] = None
        if advanced:
            subject_dd = ft.Dropdown(
                label="Бейіндік пәндер жұбы",
                options=[dropdown_option(p) for p in pair_labels],
                value="Математика - Информатика" if "Математика - Информатика" in pair_labels else pair_labels[0],
                border_radius=8,
                border_color=P.border,
                focused_border_color=P.purple,
                color=P.text,
                label_style=ft.TextStyle(color=P.muted),
                bgcolor=P.card,
            )

        type_dd = ft.Dropdown(
            label="Сұрақ түрі",
            options=[
                dropdown_option("Біртаңдаулы (1 дұрыс)", QTYPE_SINGLE),
                dropdown_option("Көп жауапты сұрақтар", QTYPE_MULTI),
                dropdown_option("Сәйкестендіру тесті", QTYPE_MATCH),
            ],
            value=QTYPE_SINGLE,
            border_radius=8,
            border_color=P.border,
            focused_border_color=P.accent,
            color=P.text,
            label_style=ft.TextStyle(color=P.muted),
            bgcolor=P.card,
        )
        if not advanced:
            type_dd.visible = False
            type_dd.value = QTYPE_SINGLE

        draft: list[Question] = []
        questions_list = ft.Column(spacing=10, controls=[muted("Әзірге сұрақ қосылмаған")])

        q_text = field("Сұрақ мәтіні", multiline=True, min_lines=2, max_lines=4)
        choice_fields = [field(f"Жауап {i + 1}") for i in range(4)]
        correct_dd = ft.Dropdown(
            label="Дұрыс жауап №",
            options=[dropdown_option(str(i + 1)) for i in range(4)],
            value="1",
            border_radius=8,
            border_color=P.border,
            focused_border_color=P.accent,
            color=P.text,
            label_style=ft.TextStyle(color=P.muted),
            width=160,
            bgcolor=P.card,
        )
        multi_checks = [
            ft.Checkbox(label=f"№{i + 1} дұрыс", value=False, fill_color=P.accent, label_style=ft.TextStyle(color=P.text, size=12))
            for i in range(4)
        ]
        left_fields = [field(f"A баған {i + 1}") for i in range(4)]
        right_fields = [field(f"B баған {i + 1} (сәйкес)") for i in range(4)]
        explanation_field = field("Түсініктеме (міндетті емес)", accent=P.purple) if advanced else None

        choices_box = ft.Column([muted("Жауап нұсқалары"), *choice_fields], spacing=8)
        single_box = ft.Column([correct_dd], spacing=8)
        multi_box = ft.Column(
            [muted("Бірнеше дұрыс жауапты белгілеңіз"), ft.Row(multi_checks, wrap=True)],
            spacing=8,
            visible=False,
        )
        match_box = ft.Column(
            [
                muted("Сәйкестікті орнатыңыз (А бағаны -> В бағаны)"),
                ft.Row(
                    [
                        ft.Column(left_fields, spacing=6, expand=1),
                        ft.Column(right_fields, spacing=6, expand=1),
                    ],
                    spacing=12,
                ),
            ],
            spacing=8,
            visible=False,
        )

        def on_type_change(e: ft.ControlEvent) -> None:
            t = type_dd.value
            single_box.visible = t == "single"
            multi_box.visible = t == "multiple"
            match_box.visible = t == "match"
            self.page.update()

        type_dd.on_change = on_type_change

        # Диалогты жинақтау
        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=P.card,
            title=ft.Text("➕ Жаңа сұрақ қосу", color=P.text, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column(
                    [
                        q_type_row,
                        question_field,
                        choices_box,
                        single_box,
                        multi_box,
                        match_box,
                        explanation_field,
                    ],
                    tight=True,
                    spacing=10,
                    scroll=ft.ScrollMode.AUTO,
                ),
                width=450,
                height=420,
            ),
            actions=[
                ft.TextButton(
                    "Бас тарту",
                    on_click=lambda _: close_dialog(self.page, dialog),
                    style=ft.ButtonStyle(color=P.muted),
                ),
                ft.ElevatedButton(
                    "Сақтау",
                    on_click=lambda _: close_dialog(self.page, dialog),
                    style=ft.ButtonStyle(bgcolor=P.accent, color=P.text),
                ),
            ],
            shape=ft.RoundedRectangleBorder(radius=8),
        )
        open_dialog(self.page, dialog)
