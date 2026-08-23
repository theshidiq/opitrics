"""Filter junk out of raw comments before anything expensive touches them.

This is the highest-leverage stage in the pipeline because it is free
and it decides what the models never have to look at. Every rule here
is deliberately conservative: when in doubt, keep the comment. A false
drop loses signal permanently; a false keep just costs a little compute.

Written for a multilingual corpus — Japanese comments are frequently
short by character count while still carrying real opinion, so length
rules are script-aware rather than word-count-only.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Characters in CJK scripts. A short Japanese comment can be dense with
# meaning, so these are counted differently from Latin words.
CJK_RE = re.compile(
    r"[぀-ゟ゠-ヿ一-鿿㐀-䶿가-힯]"
)

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

# "1:23" / "12:34:56" — timestamp-only comments are navigation, not opinion.
TIMESTAMP_RE = re.compile(r"^[\s\d:：\-–—、,.()（）]*$")
HAS_TIMESTAMP_RE = re.compile(r"\b\d{1,2}[:：]\d{2}(?:[:：]\d{2})?\b")

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF"
    "\U0000FE00-\U0000FE0F"
    "\U0001F900-\U0001F9FF"
    "❤⭐✅❌"
    "]+",
    flags=re.UNICODE,
)

# Low-content openers in the languages this corpus actually contains.
GREETING_PATTERNS = [
    r"^first!*$",
    r"^1st!*$",
    r"^早い$",
    r"^一番乗り",
    r"^初コメ",
    r"^おはようございます?[!！。\s]*$",
    r"^こんにちは[!！。\s]*$",
    r"^お疲れ様?です[!！。\s]*$",
    r"^ありがとうございま[すし]た?[!！。\s]*$",
    r"^すごい[!！。\s]*$",
    r"^いいね[!！。\s]*$",
    r"^わかりやすい[!！。\s]*$",
    r"^楽しみ[!！。\s]*$",
    r"^who'?s (here|watching)",
    r"^anyone (else )?(here|watching)",
    r"^(nice|great|good|awesome|amazing|cool) (video|vid|review)[!.\s]*$",
    r"^thanks?( you)?[!.\s]*$",
    r"^(lol|lmao|haha+|www+|草+)[!.\s]*$",
    # Bare agreement / acknowledgement — no stance about the car.
    r"^(はいはい|もちろん|そうですね|なるほど|確かに|それな|ですよね)[!！。ｗw\s]*$",
    r"^(草|わろた|笑+)[!！。\s]*$",
    r"^(同感|同意|賛成)[!！。\s]*$",
]
GREETING_RE = re.compile("|".join(GREETING_PATTERNS), re.IGNORECASE)

# Promotional / bot patterns.
SPAM_PATTERNS = [
    r"(?:t\.me|telegram|whatsapp|wa\.me)/",
    r"\b(?:投資|副業|稼[げぐ]|儲か)\w*\s*(?:相談|案件|情報|LINE)",
    r"\bDM\s*(?:ください|下さい|待って)",
    r"\b(?:giveaway|free\s+crypto|click\s+here|check\s+my\s+(?:channel|profile))\b",
    r"チャンネル登録(?:お願い|よろしく)",
    r"\bsub(?:scribe)?\s*(?:to|4)\s*sub\b",
]
SPAM_RE = re.compile("|".join(SPAM_PATTERNS), re.IGNORECASE)


@dataclass
class CleanStats:
    total: int = 0
    kept: int = 0
    dropped: dict[str, int] = field(default_factory=dict)

    def drop(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1

    @property
    def drop_rate(self) -> float:
        return 0.0 if not self.total else 1 - self.kept / self.total

    def report(self) -> str:
        lines = [f"  {self.total:,} in → {self.kept:,} kept ({self.drop_rate:.0%} dropped)"]
        for reason, n in sorted(self.dropped.items(), key=lambda kv: -kv[1]):
            lines.append(f"    {n:>6,}  {reason}")
        return "\n".join(lines)


def normalise(text: str) -> str:
    """Canonical form: NFKC folds full-width Latin/digits to ASCII, which
    matters because Japanese comments mix both freely."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("​", "").replace("﻿", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def content_length(text: str) -> int:
    """Approximate information content, script-aware.

    Japanese runs far denser per character than Latin runs per word, but
    not one-to-one: a 4-character reply like はいはい ("yeah yeah") is
    filler, while 燃費悪すぎ ("mileage is terrible") at 5 is a real
    complaint. Weighting CJK at roughly half a word per character puts
    both on the same scale as English word counts.

    Kanji carry more meaning than kana, so they count slightly higher —
    this is what separates 走る棺桶 ("rolling coffin", an opinion) from
    そうですね ("I see", filler) at the same character count.
    """
    kanji = len(re.findall(r"[一-鿿㐀-䶿]", text))
    kana = len(re.findall(r"[぀-ゟ゠-ヿ]", text))
    latin = len([w for w in re.sub(CJK_RE, " ", text).split() if w.strip()])
    return int(kanji * 0.9 + kana * 0.35 + latin)


def is_junk(text: str, min_length: int = 4) -> str | None:
    """Return a drop reason, or None to keep the comment."""
    if not text or not text.strip():
        return "empty"

    stripped = EMOJI_RE.sub("", text).strip()
    if not stripped:
        return "emoji only"

    if SPAM_RE.search(text):
        return "spam / promo"

    if URL_RE.search(text) and content_length(URL_RE.sub("", text)) < min_length:
        return "link only"

    if TIMESTAMP_RE.match(text):
        return "timestamp only"

    # A comment that is mostly a timestamp with a couple of words is
    # still navigation, not opinion.
    if HAS_TIMESTAMP_RE.search(text) and content_length(text) < min_length + 2:
        return "timestamp note"

    if GREETING_RE.match(stripped):
        return "greeting / filler"

    if content_length(stripped) < min_length:
        return "too short"

    # Runs like "wwwwwww" or "!!!!!!" with nothing else.
    if re.fullmatch(r"(.)\1{3,}[\s!！?？。.]*", stripped):
        return "repeated character"

    return None


@dataclass
class CleanComment:
    comment_id: str
    video_id: str
    text: str
    raw_text: str
    like_count: int
    reply_count: int
    is_reply: bool
    channel_title: str
    video_title: str
    region: str | None

    @property
    def weight(self) -> float:
        """Engagement weight — a comment with 400 likes is one opinion
        several hundred people endorsed. Log-scaled so a single viral
        comment cannot dominate a cluster outright."""
        import math

        return 1.0 + math.log1p(self.like_count)


def clean_comments(rows, min_length: int = 4) -> tuple[list[CleanComment], CleanStats]:
    """Filter and normalise raw DB rows into analysis-ready comments."""
    stats = CleanStats()
    kept: list[CleanComment] = []

    for row in rows:
        stats.total += 1
        raw = row["text"] or ""
        text = normalise(raw)

        reason = is_junk(text, min_length=min_length)
        if reason:
            stats.drop(reason)
            continue

        kept.append(
            CleanComment(
                comment_id=row["comment_id"],
                video_id=row["video_id"],
                text=text,
                raw_text=raw,
                like_count=row["like_count"] or 0,
                reply_count=row["reply_count"] or 0,
                is_reply=bool(row["parent_id"]),
                channel_title=row["channel_title"],
                video_title=row["video_title"],
                region=row["region"],
            )
        )
        stats.kept += 1

    return kept, stats
