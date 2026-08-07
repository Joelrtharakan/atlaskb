"""Unit tests for the Reciprocal Rank Fusion ranking logic (pure, no DB)."""

from app.retrieval import reciprocal_rank_fusion


def test_rrf_rewards_agreement_across_rankings():
    dense = ["a", "b", "c"]
    sparse = ["b", "a", "d"]
    fused = reciprocal_rank_fusion([dense, sparse], k=60)
    order = [cid for cid, _ in fused]
    # "a" (ranks 1,2) and "b" (ranks 2,1) appear in both and should lead.
    assert set(order[:2]) == {"a", "b"}
    assert order[0] == "b" or order[0] == "a"


def test_rrf_higher_rank_scores_more():
    fused = dict(reciprocal_rank_fusion([["x", "y", "z"]], k=60))
    assert fused["x"] > fused["y"] > fused["z"]


def test_rrf_combines_scores_additively():
    # An item present in both lists beats items present in only one.
    fused = dict(reciprocal_rank_fusion([["a", "b"], ["a", "c"]], k=60))
    assert fused["a"] > fused["b"]
    assert fused["a"] > fused["c"]


def test_rrf_deterministic_tie_break():
    # Same rank in symmetric lists -> ties broken by id ascending.
    fused = reciprocal_rank_fusion([["b", "a"], ["a", "b"]], k=60)
    assert [cid for cid, _ in fused] == ["a", "b"]


def test_rrf_empty():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []
