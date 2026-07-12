"""Tests for M1 rewrite pipeline (Retriever + Conflict Resolver + Pre-pass)."""

from translator_memory_engine.policy import Policy
from translator_memory_engine.retrieve.retriever import PolicyRetriever
from translator_memory_engine.rewrite.conflict import resolve
from translator_memory_engine.rewrite.prepass import apply_prepass
from translator_memory_engine.rewrite.rewriter import _strip_echo, build_prompt


def _policy(trigger, match, applies="deterministic", conf=0.9, pid="p_1"):
    return Policy(
        id=pid,
        type="entity-naming",
        trigger=trigger,
        match=match,
        action={"render_as": trigger},
        confidence=conf,
        evidence=[1, 2, 3],
    )


class TestRetriever:
    def test_matches_variant(self):
        p = _policy("Rondo Merchant Group", ["Rondo Merchant Group", "Anton Merchant Group"])
        r = PolicyRetriever([p])
        matched = r.retrieve("The Anton Merchant Group arrived.")
        assert len(matched) == 1
        assert matched[0].trigger == "Rondo Merchant Group"

    def test_word_boundary_avoids_substring_false_positive(self):
        # Regression: "Ian" must NOT match inside "brilliant" (caused a ch040
        # invented-subplot bug when the retriever falsely prompted the Ian policy).
        p = _policy("Ian", ["Ian", "Ian Hanover"])
        r = PolicyRetriever([p])
        assert r.retrieve("He had a brilliant idea.") == []
        assert r.retrieve("Julian laughed.") == []

    def test_whole_word_matches(self):
        p = _policy("Ian", ["Ian"])
        r = PolicyRetriever([p])
        matched = r.retrieve("Ian nodded in agreement.")
        assert len(matched) == 1
        assert matched[0].trigger == "Ian"


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
        p = _policy("Rondo Merchant Group", ["Rondo Merchant Group", "Anton Merchant Group"])
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

        out = clean_mtl_artifacts("[go away! I fed him and put him to sleep, what? money?]")
        assert out == "go away! I fed him and put him to sleep, what? money?"
        assert "[" not in out

    def test_strips_site_watermark_line(self):
        from translator_memory_engine.rewrite.clean import clean_mtl_artifacts

        out = clean_mtl_artifacts(
            "He left the hall.\n\n* * * Ranovel dot com * * *\n\nThe night was cold."
        )
        assert "ranovel" not in out.lower()
        assert "He left the hall." in out
        assert "The night was cold." in out


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


class TestPromptModes:
    def test_reference_mode_marks_published_translation(self):
        p = _policy("Dominic", ["Dominic"], applies="prompted")
        prompt = build_prompt("MTL text", [p], reference="ORIGINAL TEXT")
        assert "PUBLISHED TRANSLATION" in prompt
        assert "MACHINE TRANSLATION TO REPAIR" in prompt
        assert "ORIGINAL TEXT" in prompt

    def test_style_profile_mode_includes_excerpts(self):
        p = _policy("Dominic", ["Dominic"], applies="prompted")
        profile = ["Calron frowned.", "The elder laughed."]
        prompt = build_prompt("MTL text", [p], style_profile=profile)
        assert "NO published translation" in prompt
        assert "Calron frowned." in prompt
        assert "PUBLISHED TRANSLATION" not in prompt

    def test_fallback_mode_uses_style_anchor(self):
        p = _policy("Dominic", ["Dominic"], applies="prompted")
        prompt = build_prompt("MTL text", [p])
        assert "voice" in prompt.lower()
        assert "PUBLISHED TRANSLATION" not in prompt

    def test_prompt_includes_speaker_attribution_and_dialogue_disentanglement(self):
        p = _policy("Dominic", ["Dominic"], applies="prompted")
        prompt_ref = build_prompt("MTL text", [p], reference="ORIGINAL TEXT")
        prompt_fallback = build_prompt("MTL text", [p])
        assert "Speaker Attribution & Sentence Ownership (Dialogue Disentanglement)" in prompt_ref
        assert "Speaker Attribution & Sentence Ownership (Dialogue Disentanglement)" in prompt_fallback
    def test_prompt_includes_active_cast(self):
        p = _policy("Dominic", ["Dominic"], applies="prompted")
        active_cast = [
            {
                "canonical": "Dominic",
                "metadata": {
                    "gender": "male",
                    "race_or_identity": "Human",
                    "speech_style": "Polite"
                }
            }
        ]
        prompt = build_prompt("MTL text", [p], active_cast_entries=active_cast)
        assert "ACTIVE SCENE CAST" in prompt
        assert "- Dominic (male), Human, Polite" in prompt
        assert "Do NOT inject their background" in prompt



class TestRewriteModeSelection:
    def test_reference_forces_mode_even_without_llm_flag(self, tmp_path):
        from translator_memory_engine.rewrite.rewriter import rewrite

        policies = tmp_path / "policies.jsonl"
        policies.write_text("", encoding="utf-8")
        # No API key set -> LLM path is a no-op, but mode must still be recorded.
        res = rewrite(
            "Calron left.",
            str(policies),
            do_llm=False,
            reference_text="Calron departed.",
        )
        assert res["mode"] == "supervised_reference"

    def test_style_profile_mode(self, tmp_path):
        from translator_memory_engine.rewrite.rewriter import rewrite

        policies = tmp_path / "policies.jsonl"
        policies.write_text("", encoding="utf-8")
        res = rewrite(
            "Calron left.",
            str(policies),
            do_llm=False,
            style_profile=["Calron frowned."],
        )
        assert res["mode"] == "unsupervised_stylebank"

    def test_fallback_mode(self, tmp_path):
        from translator_memory_engine.rewrite.rewriter import rewrite

        policies = tmp_path / "policies.jsonl"
        policies.write_text("", encoding="utf-8")
        res = rewrite("Calron left.", str(policies), do_llm=False)
        assert res["mode"] == "fallback_faithful_repair"
