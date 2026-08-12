"""Deterministic (non-LLM) signal extraction from claim text.

Used both to select candidate pairs cheaply (entity-overlap similarity, so
the LLM never sees a pair about unrelated subjects) and to resolve "obvious"
numeric/date agreement or disagreement without spending a model call on it
(see ``deterministic.py``). Purely regex/set-based — no embeddings, no
network calls, safe to run on every claim unconditionally.
"""

from __future__ import annotations

import re

_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_MONTH_DATE_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\b",
    re.IGNORECASE,
)
# 3+ letters, not 4+: short acronyms and domain terms ("PTO", "SLA", "API",
# "cap", "fee") are frequently the exact word that identifies a claim's
# subject — dropping them (an earlier 4+ cutoff) measurably hurt recall in
# eval/conflicts/run_conflict_benchmark.py by making genuinely-matching pairs
# score 0.0 similarity purely because their shared subject word was 3 letters.
_WORD_RE = re.compile(r"[A-Za-z]{3,}")

# Lexical-overlap proxy for "same topic", not a linguistic entity extractor —
# needs to be more complete now that 3-letter words are included (common
# short filler words like "the"/"and"/"for" would otherwise inflate overlap
# between genuinely unrelated claims that just share grammar, not subject).
_STOPWORDS = frozenset(
    {
        "the", "and", "for", "are", "was", "not", "any", "all", "may", "per",
        "but", "you", "our", "its", "who", "how", "can", "now", "yet",
        "this", "that", "these", "those", "with", "from", "have", "has",
        "were", "been", "will", "would", "could", "should", "must", "shall",
        "their", "there", "which", "when", "where", "what", "your", "than",
        "also", "into", "onto", "such", "about", "each", "some", "more",
        "most", "only", "same", "over", "under", "between", "through",
    }
)


def extract_numbers(text: str) -> list[float]:
    return [float(m) for m in _NUMBER_RE.findall(text)]


def extract_dates(text: str) -> list[str]:
    """Years and month+day phrases, as their literal matched strings (not
    parsed to a date type — good enough to detect "same date mentioned" vs
    "different date mentioned", not for date arithmetic)."""
    dates = list(_MONTH_DATE_RE.findall(text))
    dates.extend(_YEAR_RE.findall(text))
    return dates


def extract_entities(text: str) -> set[str]:
    """Lowercased, stopword-filtered significant words — a cheap bag-of-words
    proxy for "topic", used only to rank/filter candidate pairs, never to
    classify a relationship on its own."""
    return {w.lower() for w in _WORD_RE.findall(text) if w.lower() not in _STOPWORDS}


def topic_similarity(a_entities: set[str], b_entities: set[str]) -> float:
    """Jaccard similarity over significant-word sets. 0.0 if either side has
    no significant words (nothing to compare, so never a candidate)."""
    if not a_entities or not b_entities:
        return 0.0
    union = a_entities | b_entities
    if not union:
        return 0.0
    return len(a_entities & b_entities) / len(union)
