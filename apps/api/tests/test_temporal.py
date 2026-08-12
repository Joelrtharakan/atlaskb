"""Temporal/historical query intent + version resolution (Trust Layer Phase 2)."""

from __future__ import annotations

import io
from datetime import UTC, datetime

from app.temporal import (
    DiffKind,
    TemporalIntent,
    classify_temporal_intent,
    diff_versions,
    resolve_two_versions,
    resolve_version_reference,
    summarize_diff,
)


def _version(number: int, *, current: bool = False, created_at=None):
    class _V:
        pass

    v = _V()
    v.version_number = number
    v.is_current_version = current
    v.created_at = created_at or datetime(2020 + number, 1, 1, tzinfo=UTC)
    v.id = f"v{number}"
    v.document_id = "doc-1"
    return v


class _Chunk:
    def __init__(self, chunk_index: int, text: str, id_: str | None = None):
        self.chunk_index = chunk_index
        self.text = text
        self.id = id_ or f"c{chunk_index}"


# --- classify_temporal_intent ---


def test_classify_current_default_no_signal():
    assert classify_temporal_intent("What is the PTO policy?") == TemporalIntent.CURRENT


def test_classify_current_explicit_keyword_wins_over_incidental_year():
    # A real question from eval/dataset.json — must never misfire as VERSION_SPECIFIC
    # just because it mentions a document title containing a year.
    q = (
        "According to the April 2025 all-hands notes, how many days per month "
        "does PTO accrue under the current company-wide policy?"
    )
    assert classify_temporal_intent(q) == TemporalIntent.CURRENT


def test_classify_version_specific_explicit_number():
    assert classify_temporal_intent("What did version 2 say about PTO?") == TemporalIntent.VERSION_SPECIFIC


def test_classify_version_specific_ordinal():
    assert classify_temporal_intent("What did the first version say?") == TemporalIntent.VERSION_SPECIFIC


def test_classify_version_specific_previous():
    assert (
        classify_temporal_intent("What did the previous version of the policy say?")
        == TemporalIntent.VERSION_SPECIFIC
    )


def test_classify_version_specific_year_version_phrase():
    assert classify_temporal_intent("What did the 2023 version say?") == TemporalIntent.VERSION_SPECIFIC


def test_classify_historical():
    assert (
        classify_temporal_intent("What did the policy used to say about remote work?")
        == TemporalIntent.HISTORICAL
    )


def test_classify_change_summary():
    assert classify_temporal_intent("What changed in the onboarding checklist?") == TemporalIntent.CHANGE_SUMMARY
    assert (
        classify_temporal_intent("When was the remote work rule introduced?")
        == TemporalIntent.CHANGE_SUMMARY
    )


def test_classify_compare_versions_with_two_numbers():
    assert (
        classify_temporal_intent("Compare version 1 and version 2 of the policy")
        == TemporalIntent.COMPARE_VERSIONS
    )


def test_classify_compare_versions_with_two_years():
    assert (
        classify_temporal_intent("What's the difference between the 2023 and 2025 policies?")
        == TemporalIntent.COMPARE_VERSIONS
    )


def test_classify_unknown_when_compare_word_but_unresolvable():
    assert classify_temporal_intent("Can you compare the policies?") == TemporalIntent.UNKNOWN


# --- resolve_version_reference ---


def test_resolve_by_explicit_number():
    versions = [_version(1), _version(2, current=True)]
    result = resolve_version_reference("What did version 1 say?", versions)
    assert result.version is not None
    assert result.version.version_number == 1


def test_resolve_nonexistent_version_returns_none_with_reason():
    versions = [_version(1), _version(2, current=True)]
    result = resolve_version_reference("What did version 5 say?", versions)
    assert result.version is None
    assert "5" in result.reason
    assert "doesn't exist" in result.reason


def test_resolve_previous_version():
    versions = [_version(1), _version(2, current=True)]
    result = resolve_version_reference("What did the previous version say?", versions)
    assert result.version is not None
    assert result.version.version_number == 1


def test_resolve_previous_version_when_only_one_version_exists():
    versions = [_version(1, current=True)]
    result = resolve_version_reference("What did the previous version say?", versions)
    assert result.version is None
    assert "only version" in result.reason


def test_resolve_by_year():
    versions = [_version(1, created_at=datetime(2023, 6, 1, tzinfo=UTC)), _version(2, current=True)]
    result = resolve_version_reference("What did the 2023 version say?", versions)
    assert result.version is not None
    assert result.version.version_number == 1


def test_resolve_by_year_no_match():
    versions = [_version(1, created_at=datetime(2023, 6, 1, tzinfo=UTC)), _version(2, current=True)]
    result = resolve_version_reference("What did the 2019 version say?", versions)
    assert result.version is None
    assert "2019" in result.reason


def test_resolve_unresolvable_reference():
    versions = [_version(1), _version(2, current=True)]
    result = resolve_version_reference("What did the policy used to say?", versions)
    assert result.version is None


# --- resolve_two_versions ---


def test_resolve_two_versions_explicit_numbers():
    versions = [_version(1), _version(2), _version(3, current=True)]
    old, new = resolve_two_versions("Compare version 1 and version 2", versions)
    assert old.version.version_number == 1
    assert new.version.version_number == 2


def test_resolve_two_versions_defaults_to_current_vs_previous():
    versions = [_version(1), _version(2, current=True)]
    old, new = resolve_two_versions("What changed?", versions)
    assert old.version.version_number == 1
    assert new.version.version_number == 2


def test_resolve_two_versions_single_document_has_nothing_to_compare():
    versions = [_version(1, current=True)]
    old, new = resolve_two_versions("What changed?", versions)
    assert old.version is None
    assert new.version is None


def test_resolve_two_versions_nonexistent_number():
    versions = [_version(1), _version(2, current=True)]
    old, new = resolve_two_versions("Compare version 1 and version 9", versions)
    assert old.version is not None
    assert new.version is None
    assert "9" in new.reason


# --- diff_versions ---


def test_diff_versions_unchanged():
    old = [_Chunk(0, "PTO is 20 days.")]
    new = [_Chunk(0, "PTO is 20 days.")]
    entries = diff_versions(old, new)
    assert len(entries) == 1
    assert entries[0].kind == DiffKind.UNCHANGED


def test_diff_versions_added_and_removed():
    old = [_Chunk(0, "Intro text.")]
    new = [_Chunk(0, "Intro text."), _Chunk(1, "New section.")]
    entries = diff_versions(old, new)
    kinds = {e.chunk_index: e.kind for e in entries}
    assert kinds[0] == DiffKind.UNCHANGED
    assert kinds[1] == DiffKind.ADDED


def test_diff_versions_removed():
    old = [_Chunk(0, "Intro."), _Chunk(1, "Old section.")]
    new = [_Chunk(0, "Intro.")]
    entries = diff_versions(old, new)
    kinds = {e.chunk_index: e.kind for e in entries}
    assert kinds[1] == DiffKind.REMOVED


def test_diff_versions_conflicting_numeric_change():
    old = [_Chunk(0, "Employees receive 20 days of annual leave.")]
    new = [_Chunk(0, "Employees receive 25 days of annual leave.")]
    entries = diff_versions(old, new)
    assert entries[0].kind == DiffKind.CONFLICTING


def test_diff_versions_plain_reword_is_changed_not_conflicting():
    old = [_Chunk(0, "Employees submit requests through HR.")]
    new = [_Chunk(0, "Employees submit requests through the HR portal.")]
    entries = diff_versions(old, new)
    assert entries[0].kind == DiffKind.CHANGED


def test_summarize_diff_no_differences():
    old = [_Chunk(0, "Same text.")]
    new = [_Chunk(0, "Same text.")]
    entries = diff_versions(old, new)
    summary = summarize_diff(entries, old_label="version 1", new_label="version 2")
    assert "No content differences" in summary


def test_summarize_diff_mentions_conflicts():
    old = [_Chunk(0, "Employees receive 20 days of annual leave.")]
    new = [_Chunk(0, "Employees receive 25 days of annual leave.")]
    entries = diff_versions(old, new)
    summary = summarize_diff(entries, old_label="version 1", new_label="version 2")
    assert "conflict" in summary.lower()


# --- /chat integration ---

V1_TEXT = "# Onboarding\n\nNew hires complete onboarding within 5 business days.\n"
V2_TEXT = "# Onboarding\n\nNew hires complete onboarding within 10 business days.\n"


def _upload(client, headers, text: str, filename: str = "onboarding.md"):
    return client.post(
        "/documents", headers=headers,
        files={"file": (filename, io.BytesIO(text.encode()), "text/markdown")},
    )


def test_chat_version_specific_question_answers_from_that_version_only(
    client, auth_headers, ingest_inline, stub_llm
):
    r1 = _upload(client, auth_headers, V1_TEXT)
    doc_id = r1.json()["id"]
    client.post(
        f"/documents/{doc_id}/reupload", headers=auth_headers,
        files={"file": ("onboarding.md", io.BytesIO(V2_TEXT.encode()), "text/markdown")},
    )

    r = client.post(
        "/chat", headers=auth_headers, json={"question": "What did version 1 say about onboarding?"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["temporal"] is not None
    assert body["temporal"]["intent"] == "VERSION_SPECIFIC"
    assert body["temporal"]["resolved_version_number"] == 1


def test_chat_nonexistent_version_returns_explicit_refusal_not_current_content(
    client, auth_headers, ingest_inline, stub_llm
):
    _upload(client, auth_headers, V1_TEXT)

    r = client.post(
        "/chat", headers=auth_headers, json={"question": "What did version 99 say about onboarding?"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["answerable"] is False
    assert "99" in body["answer"]
    assert "doesn't exist" in body["answer"]
    # Never silently answer with current-version content instead.
    assert body["citations"] == []


def test_chat_change_summary_returns_structured_diff(client, auth_headers, ingest_inline, stub_llm):
    r1 = _upload(client, auth_headers, V1_TEXT)
    doc_id = r1.json()["id"]
    client.post(
        f"/documents/{doc_id}/reupload", headers=auth_headers,
        files={"file": ("onboarding.md", io.BytesIO(V2_TEXT.encode()), "text/markdown")},
    )

    r = client.post(
        "/chat", headers=auth_headers, json={"question": "What changed in the onboarding checklist?"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["answerable"] is True
    assert body["temporal"]["intent"] == "CHANGE_SUMMARY"
    assert body["temporal"]["diff"] is not None
    assert body["temporal"]["compared_version_numbers"] == [1, 2]


def test_chat_current_question_unaffected_by_temporal_path(client, auth_headers, ingest_inline, stub_llm):
    """A completely ordinary question must produce temporal=None — the
    Phase 2 branch must never engage on a ordinary current-version question."""
    _upload(client, auth_headers, V1_TEXT)
    r = client.post("/chat", headers=auth_headers, json={"question": "What is the onboarding policy?"})
    assert r.status_code == 200
    assert r.json()["temporal"] is None
