"""Tests for M1 rewrite pipeline (Retriever + Conflict Resolver + Pre-pass)."""

from translator_memory_engine.policy import Policy
from translator_memory_engine.retrieve.retriever import PolicyRetriever
from translator_memory_engine.rewrite.conflict import resolve
from translator_memory_engine.rewrite.prepass import apply_prepass
from translator_memory_engine.rewrite.rewriter import build_prompt, _strip_echo


def _policy(trigger, match, applies="deterministic", conf=0.9, pid="p_1"):
    return Policy(
        id=pid, type="entity-naming", trigger=trigger, match=match,
        action={"render_as": trigger}, confidence=conf, evidence=[1, 2, 3],
    )


class TestRetriever:
    def test_matches_variant(self):
        p = _policy("Rondo Merchant Group",
                    ["Rondo Merchant Group", "Anton Merchant Group"])
        r = PolicyRetriever([p])
        matched = r.retrieve("The Anton Merchant Group arrived.")
        assert len(matched) == 1
        assert matched[0].trigger == "Rondo Merchant Group"


class TestConflictResolver:
    def test_higher_confidence_wins_on_overlap(self):
        # Overlapping spans: "Master" (weak) is contained in "Young Master" (strong)
        weak = _policy("Master", ["Master"], conf=0.5, pid="p_w")
        strong = _policy("Young Master", ["Young Master"], conf=0.95, pid="p_s")
        text = "The Young Master arrived."
        res = resolve(text, [weak, strong])
        assert any(c["loser_id"] == "p_w" for c in res.conflicts)
        winner_ids = {w.policy.id for w in res.winners}
        assert "p_s" in winner_ids

    def test_same_policy_overlap_not_a_conflict(self):
        p = _policy("Korea", ["Korea", "Korean"])
        text = "He spoke Korean in Korea."
        res = resolve(text, [p])
        assert res.conflicts == []  # self-overlap must not be a conflict


class TestPrepass:
    def test_substitutes_variant(self):
        p = _policy("Rondo Merchant Group",
                    ["Rondo Merchant Group", "Anton Merchant Group"])
        text = "The Anton Merchant Group arrived."
        res = resolve(text, [p])
        out, trace = apply_prepass(text, res)
        assert "Rondo Merchant Group" in out
        assert "Anton Merchant Group" not in out
        assert trace[0]["policy"] == "p_1"
        assert trace[0]["original"] == "Anton Merchant Group"

    def test_no_op_when_canonical_already_used(self):
        p = _policy("Anton", ["Anton"])
        text = "Anton left."
        res = resolve(text, [p])
        out, trace = apply_prepass(text, res)
        assert out == text
        assert trace == []  # nothing to change

    def test_prompted_policies_not_in_prepass(self):
        p = _policy("Dominic", ["Dominic"], applies="prompted")
        text = "Dominic left."
        res = resolve(text, [p])
        out, trace = apply_prepass(text, res)
        assert out == text  # prompted -> not substituted by pre-pass


class TestPromptBuilder:
    def test_includes_prompted_instructions(self):
        p = _policy("Dominic", ["Dominic"], applies="prompted")
        prompt = build_prompt("Dominic left.", [p])
        assert "Dominic" in prompt


class TestMtlCleaner:
    def test_unwraps_bracketed_thoughts(self):
        from translator_memory_engine.rewrite.clean import clean_mtl_artifacts
        out = clean_mtl_artifacts(
            "[go away! I fed him and put him to sleep, what? money?]"
        )
        assert out == "go away! I fed him and put him to sleep, what? money?"
        assert "[" not in out


class TestStripEcho:
    def test_strips_repaired_text_preface(self):
        assert _strip_echo("Here is the repaired text:\n\nThe pony left.") == "The pony left."

    def test_strips_chapter_to_rewrite_label(self):
        out = _strip_echo("Some intro\nCHAPTER TO REWRITE:\nThe bell rang.")
        assert out == "The bell rang."
        assert "CHAPTER TO REWRITE" not in out

    def test_strips_code_fence(self):
        assert _strip_echo("```\nThe cart moved.\n```") == "The cart moved."

    def test_passthrough_clean_text(self):
        assert _strip_echo("The village was quiet.") == "The village was quiet."
