"""Tests for the LLM verification backend (PLAN.md §7 / §12).

The LLM call is mocked so the verdict-application logic is tested deterministically.
"""

import json

from translator_memory_engine.policy import Policy
from translator_memory_engine.policy.verifier import LLMVerifier


def _make_policy(trigger, pid="p_001", confidence=0.9):
    return Policy(
        id=pid,
        type="entity-naming",
        trigger=trigger,
        match=[trigger],
        action={"render_as": trigger},
        confidence=confidence,
        evidence=[1, 2],
        contexts=["Example sentence with " + trigger + "."],
    )


def _mock_verifier(response_json):
    """LLMVerifier whose _call_llm returns a fixed JSON array."""
    v = LLMVerifier(api_key="test", model="m", base_url="http://x")
    v._call_llm = lambda prompt: response_json
    return v


class TestVerifierVerdicts:
    def test_keep_writes_note(self):
        p = _make_policy("Anton")
        v = _mock_verifier(json.dumps([{"id": "p_001", "verdict": "KEEP",
                                        "reason": "character name"}]))
        out = v.verify_policies([p])
        assert out[0].note == "character name"
        assert out[0].llm_rejected is False

    def test_retype_changes_type(self):
        p = _make_policy("Sir Knight")
        v = _mock_verifier(json.dumps([{"id": "p_001", "verdict": "RETYPE",
                                        "correct_type": "honorific",
                                        "reason": "honorific form"}]))
        out = v.verify_policies([p])
        assert out[0].type == "honorific"
        assert out[0].llm_rejected is False

    def test_drop_is_retained_not_deleted(self):
        # DROP must NOT delete the policy; it is flagged llm_rejected and kept
        # (for human review), and forced out of deterministic application.
        p = _make_policy("Centipede")
        v = _mock_verifier(json.dumps([{"id": "p_001", "verdict": "DROP",
                                        "reason": "generic insect term"}]))
        out = v.verify_policies([p])
        assert len(out) == 1
        assert out[0].llm_rejected is True
        assert out[0].note == "generic insect term"
        assert out[0].applies == "prompted"

    def test_drop_excluded_from_glossary(self):
        from translator_memory_engine.memory.store import PolicyStore
        p = _make_policy("Centipede")
        v = _mock_verifier(json.dumps([{"id": "p_001", "verdict": "DROP",
                                        "reason": "generic insect term"}]))
        out = v.verify_policies([p])
        store = PolicyStore()
        for pol in out:
            store.add(pol)
        glossary = store.export_glossary()
        assert all(not g.get("canonical") == "Centipede" for g in glossary)

    def test_audit_log_written(self):
        import os
        import tempfile
        p = _make_policy("Anton")
        v = _mock_verifier(json.dumps([{"id": "p_001", "verdict": "DROP",
                                        "reason": "x"}]))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "verification.jsonl")
            v.verify_policies([p], audit_path=path)
            assert os.path.exists(path)
            recs = [json.loads(l) for l in open(path)]
            assert recs[0]["id"] == "p_001"
            assert recs[0]["verdict"] == "DROP"


def _two_policies():
    a = Policy(id="p_a", type="entity-naming", trigger="Carlon", match=["Carlon"],
               action={"render_as": "Carlon"}, confidence=0.5, evidence=[1, 2],
               needs_review=True, contexts=["Carlon spoke."])
    b = Policy(id="p_b", type="entity-naming", trigger="Calron", match=["Calron"],
               action={"render_as": "Calron"}, confidence=0.99, evidence=[1, 2, 3],
               needs_review=True, contexts=["Calron spoke."])
    return a, b


class TestRefinedReview:
    def test_merge_into_resolves_variant(self):
        a, b = _two_policies()
        v = LLMVerifier(api_key="t", model="m", base_url="x")
        v._call_llm = lambda prompt: json.dumps([
            {"id": "p_a", "decision": "MERGE_INTO", "target_id": "p_b",
             "reason": "spelling variant"},
        ])
        out = v.review_ambiguous([a, b])
        triggers = {p.trigger for p in out}
        assert "Calron" in triggers
        assert "Carlon" not in triggers  # merged away
        assert any("Carlon" in p.match for p in out)  # alias retained

    def test_mutual_merge_keeps_best_root(self):
        a, b = _two_policies()
        # Each says merge into the other -> cycle; must keep the higher-confidence root
        v = LLMVerifier(api_key="t", model="m", base_url="x")
        v._call_llm = lambda prompt: json.dumps([
            {"id": "p_a", "decision": "MERGE_INTO", "target_id": "p_b"},
            {"id": "p_b", "decision": "MERGE_INTO", "target_id": "p_a"},
        ])
        out = v.review_ambiguous([a, b])
        triggers = {p.trigger for p in out}
        assert "Calron" in triggers          # higher confidence survives
        assert "Carlon" not in triggers
        assert len(out) == 1

    def test_keep_clears_needs_review(self):
        a, b = _two_policies()
        v = LLMVerifier(api_key="t", model="m", base_url="x")
        v._call_llm = lambda prompt: json.dumps([
            {"id": "p_a", "decision": "KEEP", "reason": "distinct"},
        ])
        out = v.review_ambiguous([a, b])
        kept = [p for p in out if p.id == "p_a"][0]
        assert kept.needs_review is False

    def test_drop_marks_rejected(self):
        a, b = _two_policies()
        v = LLMVerifier(api_key="t", model="m", base_url="x")
        v._call_llm = lambda prompt: json.dumps([
            {"id": "p_a", "decision": "DROP", "reason": "false positive"},
        ])
        out = v.review_ambiguous([a, b])
        dropped = [p for p in out if p.id == "p_a"][0]
        assert dropped.llm_rejected is True

