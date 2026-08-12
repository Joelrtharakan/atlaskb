"""Cross-document conflict detection (Trust Layer T4)."""

from __future__ import annotations

import io
import json

from app.llm import TokenUsage, detect_conflicts
from app.retrieval import RetrievedChunk


def _chunk(cid: str, doc: str, text: str = "text") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=cid, document_id=doc, version_id="v1", text=text, page_num=1, section=None, score=1.0
    )


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]
        self.usage = None


class _FakeClient:
    def __init__(self, content: str):
        self._content = content
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        return _FakeCompletion(self._content)


def test_single_document_skips_llm_call(monkeypatch):
    def _boom():
        raise AssertionError("should not call the LLM for a single-document chunk set")

    monkeypatch.setattr("app.llm._client", _boom)
    chunks = [_chunk("c1", "doc-a"), _chunk("c2", "doc-a")]
    conflicts, usage = detect_conflicts(chunks)
    assert conflicts == []
    assert usage == TokenUsage()


def test_detects_cross_document_conflict(monkeypatch):
    content = json.dumps(
        {
            "conflicts": [
                {
                    "topic": "PTO accrual",
                    "description": "One source says 14 days, another says unlimited.",
                    "chunk_ids": ["c1", "c2"],
                }
            ]
        }
    )
    monkeypatch.setattr("app.llm._client", lambda: _FakeClient(content))
    chunks = [_chunk("c1", "doc-a", "14 days"), _chunk("c2", "doc-b", "unlimited PTO")]
    conflicts, _usage = detect_conflicts(chunks)
    assert len(conflicts) == 1
    assert conflicts[0]["topic"] == "PTO accrual"
    assert set(conflicts[0]["chunk_ids"]) == {"c1", "c2"}
    assert set(conflicts[0]["document_ids"]) == {"doc-a", "doc-b"}


def test_same_document_only_conflict_is_dropped(monkeypatch):
    # The model incorrectly (or the chunk set) points at chunks from one document —
    # not a lineage conflict, so it must not surface as one.
    content = json.dumps(
        {"conflicts": [{"topic": "x", "description": "y", "chunk_ids": ["c1", "c3"]}]}
    )
    monkeypatch.setattr("app.llm._client", lambda: _FakeClient(content))
    chunks = [_chunk("c1", "doc-a"), _chunk("c2", "doc-b"), _chunk("c3", "doc-a")]
    conflicts, _usage = detect_conflicts(chunks)
    assert conflicts == []


def test_unknown_chunk_ids_filtered_out(monkeypatch):
    content = json.dumps(
        {"conflicts": [{"topic": "x", "description": "y", "chunk_ids": ["c1", "ghost"]}]}
    )
    monkeypatch.setattr("app.llm._client", lambda: _FakeClient(content))
    chunks = [_chunk("c1", "doc-a"), _chunk("c2", "doc-b")]
    conflicts, _usage = detect_conflicts(chunks)
    # "ghost" isn't a real chunk and "c1" alone can't form a cross-doc conflict.
    assert conflicts == []


def test_llm_failure_degrades_to_no_conflicts(monkeypatch):
    def _raise():
        raise RuntimeError("LLM unreachable")

    monkeypatch.setattr("app.llm._client", _raise)
    chunks = [_chunk("c1", "doc-a"), _chunk("c2", "doc-b")]
    conflicts, usage = detect_conflicts(chunks)
    assert conflicts == []
    assert usage == TokenUsage()


PTO_HR = "# PTO Policy\n\nPTO accrues at 1.5 days per month, capped at 18 days per year.\n"
PTO_ENG = "# Engineering Time Off\n\nEngineering is unlimited PTO with no accrual cap.\n"


def test_chat_surfaces_conflicts_end_to_end(client, auth_headers, ingest_inline, monkeypatch):
    """Upload two genuinely conflicting docs, stub the answer LLM call, stub the
    structured conflict pipeline to reflect that disagreement, and check it
    reaches the chat response (Trust Layer Phase 1: chat.py now calls
    detect_conflicts_structured, not app.llm.detect_conflicts)."""
    from app.conflict_detection.types import Relationship, StructuredConflict
    from app.llm import Assessment, GroundedAnswer

    def fake_assess(question, chunks):
        return Assessment(sufficient=True, refined_query=None)

    def fake_generate(question, chunks):
        return GroundedAnswer(
            True,
            "PTO policy varies by team.",
            [{"claim": "supported", "chunk_ids": [chunks[0].chunk_id]}],
        )

    def fake_detect_conflicts_structured(chunks):
        doc_ids = {c.document_id for c in chunks}
        if len(doc_ids) < 2:
            return [], TokenUsage()
        a, b = chunks[0], chunks[1]
        return (
            [
                StructuredConflict(
                    topic="PTO accrual",
                    document_id_a=a.document_id,
                    document_version_a=a.version_id,
                    chunk_id_a=a.chunk_id,
                    claim_a=a.text,
                    document_id_b=b.document_id,
                    document_version_b=b.version_id,
                    chunk_id_b=b.chunk_id,
                    claim_b=b.text,
                    relationship=Relationship.CONTRADICTS,
                    confidence=0.92,
                    explanation="HR policy caps PTO at 18 days; Engineering says unlimited.",
                    method="deterministic",
                )
            ],
            TokenUsage(),
        )

    monkeypatch.setattr("app.llm.assess_context", fake_assess)
    monkeypatch.setattr("app.llm.generate_answer", fake_generate)
    monkeypatch.setattr(
        "app.routers.chat.detect_conflicts_structured", fake_detect_conflicts_structured
    )

    client.post(
        "/documents", headers=auth_headers,
        files={"file": ("hr.md", io.BytesIO(PTO_HR.encode()), "text/markdown")},
    )
    client.post(
        "/documents", headers=auth_headers,
        files={"file": ("eng.md", io.BytesIO(PTO_ENG.encode()), "text/markdown")},
    )

    r = client.post("/chat", headers=auth_headers, json={"question": "How much PTO do I get?"})
    assert r.status_code == 200
    body = r.json()
    assert body["conflicts"]
    assert body["conflicts"][0]["topic"] == "PTO accrual"
    assert len(body["conflicts"][0]["document_ids"]) == 2
    assert body["conflicts"][0]["relationship"] == "CONTRADICTS"
    assert body["conflicts"][0]["confidence"] == 0.92
