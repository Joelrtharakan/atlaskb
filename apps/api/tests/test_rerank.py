"""Unit tests for the (fake-backend) reranker — pure, no model download."""

from app.rerank import score


def test_score_ranks_higher_overlap_first():
    query = "refund policy days"
    texts = [
        "The weather today is sunny with a light breeze.",
        "Refunds are issued within 14 days of purchase per policy.",
    ]
    scores = score(query, texts)
    assert scores[1] > scores[0]


def test_score_empty_texts_returns_empty():
    assert score("anything", []) == []


def test_score_no_overlap_is_zero():
    scores = score("refund policy", ["completely unrelated content here"])
    assert scores == [0.0]
