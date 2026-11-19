"""نرمال‌سازی فارسی و شباهت متنی برای لایه معنایی پژوهشیار۳۶۰.

ابزارهای تعیین‌شده و بدون وابستگی بیرونی — برای استانداردسازی (بخش ۵.۲ سند)،
Block-bing تطبیق موجودیت (۵.۳) و جست‌وجوی ترکیبی (۱۰.۲). همهٔ توابع
خالص و بدون حالت هستند تا در خروجی‌های نسخه‌دار قابل بازتولید باشند.
"""
from __future__ import annotations

import re
import unicodedata
from math import log

# ------------------------------------------------ نرمال‌سازی متن فارسی
_ARABIC_MAP = str.maketrans({
    "ي": "ی", "ك": "ک", "ى": "ی", "ۀ": "ه", "ة": "ه",
    "ؤ": "و", "إ": "ا", "أ": "ا", "آ": "ا",  # همزه و آ → الف (برای کلید تطبیق)
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
})
_ZWNJ = "\u200c"
_PUNCT = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff]+|[\(\)\[\]\{\}«»\"'`;:,\.!؟?·…\-–—_/\\|]+")
_SPACES = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    """نرمال‌سازی برای تطبیق و جست‌وجو: ي/ی، ك/ک، همزه، ارقام، نیم‌فاصلهٔ تکراری، فاصله."""
    if not s:
        return ""
    s = unicodedata.normalize("NFC", str(s)).translate(_ARABIC_MAP)
    s = s.replace(_ZWNJ, " ")          # نیم‌فاصله → فاصله در کلید تطبیق
    s = _PUNCT.sub(" ", s)
    s = _SPACES.sub(" ", s).strip().lower()
    return s


def keep_display(s: str) -> str:
    """نام اصلی برای نمایش (نیم‌فاصله حفظ می‌شود) — فقط فاصلهٔ اضافی جمع می‌شود."""
    if not s:
        return ""
    s = unicodedata.normalize("NFC", str(s)).translate(_ARABIC_MAP)
    return _SPACES.sub(" ", s.replace(_ZWNJ, "‌").strip())


_STOP = {
    "و", "در", "به", "از", "که", "این", "با", "برای", "های", "است", "را", "یک",
    "the", "of", "and", "in", "for", "on", "a", "an", "with", "to", "is",
}


def tokenize(s: str) -> list[str]:
    n = normalize_text(s)
    return [t for t in n.split() if t and t not in _STOP and len(t) > 1]


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def name_similarity(n1: str, n2: str) -> float:
    """شباهت نام‌اشخاص: ترکیب ژاکارد توکن‌ها + تطابق ترتیبی نام/نام‌خانوادگی.

    به‌تنهایی برای ادغام کافی نیست (سند ۵.۳) — فقط شاهد کمکی است.
    """
    t1, t2 = tokenize(n1), tokenize(n2)
    base = jaccard(set(t1), set(t2))
    # تطابق ترتیبی: به‌اشتراک‌گذاری توکن در جایگاه نخست (نام) و آخر (نام‌خانوادگی)
    order = 0.0
    if t1 and t2:
        if t1[0] == t2[0]:
            order += 0.15
        if t1[-1] == t2[-1]:
            order += 0.15
    return min(1.0, base + order)


# ------------------------------------------------ TF-IDF سبک برای جست‌وجوی ترکیبی
def _tf(tokens: list[str]) -> dict[str, float]:
    d: dict[str, float] = {}
    for t in tokens:
        d[t] = d.get(t, 0.0) + 1.0
    n = len(tokens) or 1
    return {t: (1.0 + log(c)) / n for t, c in d.items()}


class TfidfIndex:
    """شاخص برداری سبک روی متن موجودیت‌ها — جایگزین آفلاین pgvector.

    تعیین‌شده و قابل بازتولید: با هر بازسازی projection از نو ساخته می‌شود
    و فقط روی متن‌های ثبت‌شده در دفتر ثبت معنا دارد.
    """

    def __init__(self) -> None:
        self._docs: dict[str, dict[str, float]] = {}
        self._df: dict[str, int] = {}

    def add(self, key: str, text: str) -> None:
        toks = tokenize(text)
        tf = _tf(toks)
        self._docs[key] = tf
        for t in tf:
            self._df[t] = self._df.get(t, 0) + 1

    def search(self, query: str, top_k: int = 12) -> list[tuple[str, float]]:
        q = _tf(tokenize(query))
        if not q:
            return []
        n_docs = max(len(self._docs), 1)
        scores: list[tuple[str, float]] = []
        for key, tf in self._docs.items():
            s = 0.0
            for t, qw in q.items():
                if t in tf:
                    idf = log(1.0 + n_docs / (1.0 + self._df.get(t, 0)))
                    s += qw * tf[t] * idf
            if s > 0:
                scores.append((key, s))
        scores.sort(key=lambda x: (-x[1], x[0]))
        return scores[:top_k]

    def expand_terms(self, query: str) -> set[str]:
        return set(tokenize(query))
