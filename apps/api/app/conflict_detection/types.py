"""Shared data structures for the structured conflict-detection pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Relationship(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    COMPLEMENTS = "COMPLEMENTS"
    UNRELATED = "UNRELATED"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class Claim:
    """One atomic factual assertion, attributed back to its source chunk."""

    chunk_id: str
    document_id: str
    version_id: str | None
    text: str
    numbers: list[float] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    entities: set[str] = field(default_factory=set)


@dataclass
class ConflictCandidate:
    """A cross-document claim pair selected for (deterministic or LLM)
    relationship classification, plus the lexical similarity that got it
    selected — kept for debugging/eval, not part of the final result."""

    claim_a: Claim
    claim_b: Claim
    similarity: float


@dataclass
class StructuredConflict:
    """One classified claim pair — the pipeline's final output unit. Maps
    directly onto both the persisted `conflicts` table row and (for
    CONTRADICTS results) the API's `Conflict` response schema."""

    topic: str
    document_id_a: str
    document_version_a: str | None
    chunk_id_a: str
    claim_a: str
    document_id_b: str
    document_version_b: str | None
    chunk_id_b: str
    claim_b: str
    relationship: Relationship
    confidence: float
    explanation: str
    method: str  # "deterministic" | "llm"
