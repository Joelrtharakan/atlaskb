"""Temporal/historical query intent (Trust Layer Phase 2).

Classifies whether a question is about the CURRENT document state or about
its HISTORY, and — for historical questions — resolves exactly which
document version is meant. This exists because retrieval was previously
binary: either every version is searchable at once (undifferentiated pool)
or only the current one is (the default) — there was no way for a single
chat question to target a specific historical version, and a historical
question that couldn't be resolved would either silently answer from the
current version or generically refuse, with no way to tell which happened.

CRITICAL SAFETY RULE (see app/routers/chat.py's call site): a HISTORICAL,
VERSION_SPECIFIC, COMPARE_VERSIONS, or CHANGE_SUMMARY question must NEVER be
silently answered from the current version. If the referenced version can't
be resolved, the caller must return an explicit "that version isn't
available" response — never fall back to current-version content as if the
version distinction didn't matter.

Classification is deliberately regex/keyword-based, not an LLM call: the
whole point is a *safety* boundary (never silently substitute), and a
deterministic classifier is auditable and cannot hallucinate an intent. The
tradeoff is recall on unusual phrasings — documented as a known limitation,
not hidden.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.conflict_detection.signals import extract_dates, extract_numbers
from app.models import Chunk, DocumentVersion


class TemporalIntent(str, Enum):
    CURRENT = "CURRENT"
    HISTORICAL = "HISTORICAL"
    VERSION_SPECIFIC = "VERSION_SPECIFIC"
    COMPARE_VERSIONS = "COMPARE_VERSIONS"
    CHANGE_SUMMARY = "CHANGE_SUMMARY"
    UNKNOWN = "UNKNOWN"


_COMPARE_WORDS = re.compile(
    r"\b(compare|comparison|difference between|differs? from|versus|\bvs\.?\b)\b", re.IGNORECASE
)
_CHANGE_WORDS = re.compile(
    r"\b(what changed|what'?s new|what has changed|how has .+ changed|"
    r"when was .+ (introduced|added)|was .+ (introduced|added|present) in)\b",
    re.IGNORECASE,
)
_CURRENT_WORDS = re.compile(
    r"\b(current(ly)?|latest version|now|today|as it stands|at present)\b", re.IGNORECASE
)
_VERSION_NUMBER_RE = re.compile(r"\bv(?:ersion)?\s*#?\s*(\d+)\b", re.IGNORECASE)
_ORDINAL_VERSION_RE = re.compile(
    r"\b(first|original|earliest)\s+version\b|\b(second)\s+version\b|\b(third)\s+version\b",
    re.IGNORECASE,
)
_PREVIOUS_VERSION_RE = re.compile(
    r"\b(previous|prior|old|earlier|last)\s+version\b", re.IGNORECASE
)
_YEAR_VERSION_RE = re.compile(r"\b(?:19|20)\d{2}\s+version\b|\bversion\s+(?:from\s+)?(?:19|20)\d{2}\b", re.IGNORECASE)
_HISTORICAL_WORDS = re.compile(
    r"\b(used to say|previously (said|stated|read)|in the past|historically|no longer|"
    r"what did .+ (say|used to say))\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

_ORDINAL_TO_NUMBER = {"first": 1, "original": 1, "earliest": 1, "second": 2, "third": 3}


def classify_temporal_intent(question: str) -> TemporalIntent:
    """Deterministic, conservative classification — defaults to CURRENT
    rather than misfiring into a historical code path on an ordinary
    question. Order matters: an explicit "current"/"latest" signal always
    wins over an incidental year mention elsewhere in the question (e.g. "the
    April 2025 all-hands notes" should not be misread as a version request)."""
    q = question.strip()

    has_two_version_refs = (
        len(_VERSION_NUMBER_RE.findall(q)) >= 2
        or len(_YEAR_RE.findall(q)) >= 2
        or (bool(_VERSION_NUMBER_RE.search(q)) and _CURRENT_WORDS.search(q))
        or (bool(_YEAR_RE.search(q)) and _CURRENT_WORDS.search(q))
    )
    if _COMPARE_WORDS.search(q):
        # A clear ask for a comparison, but not enough to resolve which two
        # versions — genuinely UNKNOWN, not silently treated as a current-
        # version question (chat.py routes UNKNOWN through the normal path,
        # same as CURRENT, but the label stays honest about why).
        return TemporalIntent.COMPARE_VERSIONS if has_two_version_refs else TemporalIntent.UNKNOWN

    if _CHANGE_WORDS.search(q):
        return TemporalIntent.CHANGE_SUMMARY

    if _CURRENT_WORDS.search(q):
        return TemporalIntent.CURRENT

    if (
        _VERSION_NUMBER_RE.search(q)
        or _ORDINAL_VERSION_RE.search(q)
        or _PREVIOUS_VERSION_RE.search(q)
        or _YEAR_VERSION_RE.search(q)
    ):
        return TemporalIntent.VERSION_SPECIFIC

    if _HISTORICAL_WORDS.search(q):
        return TemporalIntent.HISTORICAL

    return TemporalIntent.CURRENT


@dataclass
class VersionResolution:
    version: DocumentVersion | None
    # Human-readable reason when version is None — surfaced directly in the
    # chat refusal so the user knows *why* (not just "cannot answer").
    reason: str | None = None


def resolve_version_reference(question: str, versions: list[DocumentVersion]) -> VersionResolution:
    """Resolve which of ``versions`` (all versions of one document, any order)
    a question's version reference points to. Returns ``version=None`` with a
    human-readable ``reason`` when the reference can't be resolved — the
    caller must surface that as an explicit refusal, never substitute the
    current version."""
    if not versions:
        return VersionResolution(None, "This document has no version history.")

    ordered = sorted(versions, key=lambda v: v.version_number)
    current = next((v for v in ordered if v.is_current_version), ordered[-1])

    m = _VERSION_NUMBER_RE.search(question)
    if m:
        n = int(m.group(1))
        match = next((v for v in ordered if v.version_number == n), None)
        if match is None:
            return VersionResolution(
                None,
                f"Version {n} doesn't exist for this document — versions 1 through "
                f"{ordered[-1].version_number} are available.",
            )
        return VersionResolution(match)

    m = _ORDINAL_VERSION_RE.search(question)
    if m:
        word = next(g for g in m.groups() if g)
        n = _ORDINAL_TO_NUMBER[word.lower()]
        match = next((v for v in ordered if v.version_number == n), None)
        if match is None:
            return VersionResolution(None, f"There is no version {n} of this document.")
        return VersionResolution(match)

    if _PREVIOUS_VERSION_RE.search(question):
        idx = ordered.index(current)
        if idx == 0:
            return VersionResolution(
                None, "This is the only version of this document — there is no previous version."
            )
        return VersionResolution(ordered[idx - 1])

    m = _YEAR_VERSION_RE.search(question)
    if m:
        year_match = _YEAR_RE.search(m.group(0))
        if year_match:
            year = int(year_match.group(0))
            candidates = [v for v in ordered if v.created_at and v.created_at.year == year]
            if not candidates:
                return VersionResolution(
                    None, f"No version of this document is dated {year}."
                )
            return VersionResolution(max(candidates, key=lambda v: v.created_at))

    return VersionResolution(None, "I couldn't tell which version of this document you mean.")


def resolve_two_versions(
    question: str, versions: list[DocumentVersion]
) -> tuple[VersionResolution, VersionResolution]:
    """Resolve the (old, new) version pair for COMPARE_VERSIONS/CHANGE_SUMMARY.

    Priority: two explicit version numbers in the question > two explicit
    years > one explicit reference (paired against current) > no explicit
    reference at all (defaults to current vs. the version immediately before
    it — the natural reading of a bare "what changed?")."""
    if not versions:
        na = VersionResolution(None, "This document has no version history.")
        return na, na

    ordered = sorted(versions, key=lambda v: v.version_number)
    current = next((v for v in ordered if v.is_current_version), ordered[-1])

    version_numbers = [int(n) for n in _VERSION_NUMBER_RE.findall(question)]
    years = [int(y) for y in _YEAR_RE.findall(question)]

    def _by_number(n: int) -> VersionResolution:
        match = next((v for v in ordered if v.version_number == n), None)
        if match is None:
            return VersionResolution(
                None,
                f"Version {n} doesn't exist for this document — versions 1 through "
                f"{ordered[-1].version_number} are available.",
            )
        return VersionResolution(match)

    def _by_year(y: int) -> VersionResolution:
        candidates = [v for v in ordered if v.created_at and v.created_at.year == y]
        if not candidates:
            return VersionResolution(None, f"No version of this document is dated {y}.")
        return VersionResolution(max(candidates, key=lambda v: v.created_at))

    if len(version_numbers) >= 2:
        return _by_number(version_numbers[0]), _by_number(version_numbers[1])
    if len(years) >= 2:
        return _by_year(years[0]), _by_year(years[1])
    if len(version_numbers) == 1:
        return _by_number(version_numbers[0]), VersionResolution(current)
    if len(years) == 1:
        return _by_year(years[0]), VersionResolution(current)

    idx = ordered.index(current)
    if idx == 0:
        na = VersionResolution(None, "This is the only version of this document — there is nothing to compare.")
        return na, na
    return VersionResolution(ordered[idx - 1]), VersionResolution(current)


class DiffKind(str, Enum):
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    CHANGED = "CHANGED"
    UNCHANGED = "UNCHANGED"
    CONFLICTING = "CONFLICTING"


@dataclass
class VersionDiffEntry:
    kind: DiffKind
    chunk_index: int
    old_chunk_id: str | None
    new_chunk_id: str | None
    old_text: str | None
    new_text: str | None


def diff_versions(old_chunks: list[Chunk], new_chunks: list[Chunk]) -> list[VersionDiffEntry]:
    """Structured chunk-level diff between two versions of the same document.

    Chunks are aligned by ``chunk_index`` — a position-based alignment, not a
    content-similarity match, so a diff that inserts/removes a chunk near the
    start will shift every later index and show as CHANGED rather than a
    clean ADDED/REMOVED pair. This is a real, documented limitation (see
    apps/api/tests/test_temporal.py's diff_versions tests for exactly what
    is and isn't covered), not something a smarter but slower content-
    alignment algorithm was scoped for in this phase.

    CONFLICTING (vs. plain CHANGED) is reported when the two chunks at the
    same position assert disjoint numeric or date values — reusing the same
    deterministic signal extraction Phase 1 built for conflict detection,
    rather than a second implementation of "these numbers disagree."
    """
    by_index_old = {c.chunk_index: c for c in old_chunks}
    by_index_new = {c.chunk_index: c for c in new_chunks}
    all_indices = sorted(set(by_index_old) | set(by_index_new))

    entries: list[VersionDiffEntry] = []
    for idx in all_indices:
        old_c = by_index_old.get(idx)
        new_c = by_index_new.get(idx)
        if old_c is not None and new_c is None:
            entries.append(VersionDiffEntry(DiffKind.REMOVED, idx, old_c.id, None, old_c.text, None))
        elif old_c is None and new_c is not None:
            entries.append(VersionDiffEntry(DiffKind.ADDED, idx, None, new_c.id, None, new_c.text))
        elif old_c is not None and new_c is not None:
            if old_c.text.strip() == new_c.text.strip():
                entries.append(
                    VersionDiffEntry(DiffKind.UNCHANGED, idx, old_c.id, new_c.id, old_c.text, new_c.text)
                )
            else:
                old_nums = {round(n, 2) for n in extract_numbers(old_c.text)}
                new_nums = {round(n, 2) for n in extract_numbers(new_c.text)}
                old_dates = set(extract_dates(old_c.text))
                new_dates = set(extract_dates(new_c.text))
                numeric_conflict = old_nums and new_nums and not (old_nums & new_nums)
                date_conflict = old_dates and new_dates and not (old_dates & new_dates)
                kind = DiffKind.CONFLICTING if (numeric_conflict or date_conflict) else DiffKind.CHANGED
                entries.append(
                    VersionDiffEntry(kind, idx, old_c.id, new_c.id, old_c.text, new_c.text)
                )
    return entries


def summarize_diff(entries: list[VersionDiffEntry], *, old_label: str, new_label: str) -> str:
    """Deterministic (non-LLM) natural-language summary of a version diff —
    built directly from the structured entries so every sentence traces to a
    specific chunk, rather than an LLM narrating (and potentially misstating)
    the diff."""
    added = [e for e in entries if e.kind == DiffKind.ADDED]
    removed = [e for e in entries if e.kind == DiffKind.REMOVED]
    changed = [e for e in entries if e.kind == DiffKind.CHANGED]
    conflicting = [e for e in entries if e.kind == DiffKind.CONFLICTING]

    if not added and not removed and not changed and not conflicting:
        return f"No content differences found between {old_label} and {new_label}."

    parts = [f"Comparing {old_label} to {new_label}:"]
    if conflicting:
        parts.append(
            f"{len(conflicting)} section(s) changed with a direct factual conflict "
            f"(a number or date that disagrees, not just reworded)."
        )
    if changed:
        parts.append(f"{len(changed)} section(s) were reworded or updated.")
    if added:
        parts.append(f"{len(added)} section(s) were added.")
    if removed:
        parts.append(f"{len(removed)} section(s) were removed.")
    return " ".join(parts)
