#!/usr/bin/env python3
"""4-condition style experiment: A/B/C/D on paired chapters.

Conditions:
  A: Current baseline (hardcoded _STYLE_REFERENCE, Jaccard exemplars)
  B: +Qualitative profile (LLM-analyzed register/tone/notes)
  C: +Exemplars (embedding-based scene-matched exemplars)
  D: +Tendencies + Stylometry (editorial tendencies from diffs + deterministic metrics)

Chapters: ch001 + ch039 (both have originals for Tier-1 eval).

Usage:
    uv run python scripts/style_experiment.py \\
        --mtl-dir test-dataset/feasting-lord-in-another-world-input \\
        --original-dir test-dataset/feasting-lord-in-another-world \\
        --policies outputs/policies.jsonl \\
        --glossary outputs/glossary.json \\
        --output-dir outputs/experiment \\
        [--judge]
"""

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _chapter_num(path: str) -> Optional[int]:
    import re

    m = re.search(r"(\d+)", os.path.basename(path))
    return int(m.group(1)) if m else None


def _read_text_chapters(directory: str) -> List[str]:
    chapters = []
    for f in sorted(os.listdir(directory)):
        if f.lower().endswith(".txt"):
            with open(os.path.join(directory, f), "r", encoding="utf-8") as fh:
                chapters.append(fh.read())
    return chapters


def _index_by_chapter(directory: str) -> Dict[int, str]:
    index: Dict[int, str] = {}
    for f in sorted(os.listdir(directory)):
        if f.lower().endswith(".txt"):
            num = _chapter_num(f)
            if num is not None:
                with open(os.path.join(directory, f), "r", encoding="utf-8") as fh:
                    index[num] = fh.read()
    return index


def run_condition_a(
    mtl_text: str,
    reference_text: Optional[str],
    policies_path: str,
    glossary: Optional[List[Dict]],
    model: str,
    base_url: Optional[str],
    api_key_env: str,
) -> str:
    """Condition A: Current baseline — hardcoded style anchor, Jaccard exemplars."""
    from translator_memory_engine.rewrite.rewriter import rewrite

    result = rewrite(
        mtl_text,
        policies_path=policies_path,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
        do_llm=True,
        reference_text=reference_text,
        glossary=glossary,
    )
    return result["rewritten_text"]


def run_condition_b(
    mtl_text: str,
    reference_text: Optional[str],
    policies_path: str,
    glossary: Optional[List[Dict]],
    model: str,
    base_url: Optional[str],
    api_key_env: str,
    style_profile: List[str],
) -> str:
    """Condition B: +Qualitative profile (LLM-analyzed register/tone/notes)."""
    from translator_memory_engine.rewrite.rewriter import rewrite

    result = rewrite(
        mtl_text,
        policies_path=policies_path,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
        do_llm=True,
        reference_text=reference_text,
        style_profile=style_profile,
        glossary=glossary,
    )
    return result["rewritten_text"]


def run_condition_c(
    mtl_text: str,
    reference_text: Optional[str],
    policies_path: str,
    glossary: Optional[List[Dict]],
    model: str,
    base_url: Optional[str],
    api_key_env: str,
    exemplar_index,
    embed_fn,
) -> str:
    """Condition C: +Exemplars (embedding-based scene-matched exemplars)."""
    from translator_memory_engine.rewrite.rewriter import rewrite

    # Retrieve top exemplars using embedding similarity
    exemplars = exemplar_index.retrieve_balanced(mtl_text, embed_fn=embed_fn, per_type=3)
    style_profile = [f"[{ex.scene_type}] {ex.text}" for ex in exemplars]

    result = rewrite(
        mtl_text,
        policies_path=policies_path,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
        do_llm=True,
        reference_text=reference_text,
        style_profile=style_profile,
        glossary=glossary,
    )
    return result["rewritten_text"]


def run_condition_d(
    mtl_text: str,
    reference_text: Optional[str],
    policies_path: str,
    glossary: Optional[List[Dict]],
    model: str,
    base_url: Optional[str],
    api_key_env: str,
    exemplar_index,
    embed_fn,
    tendencies: Dict[str, str],
    diagnostics: Dict[str, float],
) -> str:
    """Condition D: +Tendencies + Stylometry (editorial patterns + deterministic metrics)."""
    from translator_memory_engine.rewrite.rewriter import rewrite

    exemplars = exemplar_index.retrieve_balanced(mtl_text, embed_fn=embed_fn, per_type=3)
    style_profile = [f"[{ex.scene_type}] {ex.text}" for ex in exemplars]
    for label, instruction in tendencies.items():
        style_profile.append(f"Tendency ({label}): {instruction}")
    if diagnostics:
        parts = [f"{k}={v:.2f}" for k, v in diagnostics.items() if k != "top_sentence_starts"]
        style_profile.append(f"Measured: {'; '.join(parts)}")

    result = rewrite(
        mtl_text,
        policies_path=policies_path,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
        do_llm=True,
        reference_text=reference_text,
        style_profile=style_profile,
        glossary=glossary,
    )
    return result["rewritten_text"]


def evaluate(gen: str, orig: str, mtl: str, canonical: List[str]) -> Dict:
    """Run all metrics on a generated chapter."""
    from translator_memory_engine.eval.align import (
        cosine,
        cosine_excluding,
        stylometry_delta,
        voice_richness_score,
    )
    from translator_memory_engine.eval.faith import faithfulness_vs_reference

    return {
        "cosine_gen_orig": cosine(gen, orig),
        "cosine_mtl_orig": cosine(mtl, orig),
        "cosine_delta": round(cosine(gen, orig) - cosine(mtl, orig), 4),
        "cosine_norm_gen_orig": cosine_excluding(gen, orig, canonical),
        "cosine_norm_mtl_orig": cosine_excluding(mtl, orig, canonical),
        "faith": faithfulness_vs_reference(gen, orig),
        "stylometry_delta": stylometry_delta(gen, orig),
        "voice_richness_gen": voice_richness_score(gen),
        "voice_richness_orig": voice_richness_score(orig),
        "voice_richness_mtl": voice_richness_score(mtl),
    }


def main():
    parser = argparse.ArgumentParser(description="4-condition style experiment")
    parser.add_argument("--mtl-dir", required=True, help="Directory of MTL chapters")
    parser.add_argument("--original-dir", required=True, help="Directory of original chapters")
    parser.add_argument("--policies", required=True, help="Path to policies.jsonl")
    parser.add_argument("--glossary", default=None, help="Path to glossary.json")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--config", default="config.yaml", help="Config file")
    parser.add_argument(
        "--chapters",
        nargs="+",
        type=int,
        default=[1, 39],
        help="Chapter numbers to test (default: 1 39)",
    )
    parser.add_argument("--judge", action="store_true", help="Enable Gemini judge")
    args = parser.parse_args()

    import yaml

    with open(args.config, "r") as f:
        config = yaml.safe_load(f)
    verify_cfg = config.get("extraction", {}).get("verification", {})
    model = verify_cfg.get("model", "llama-3.1-8b-instant")
    base_url = verify_cfg.get("base_url")
    api_key_env = verify_cfg.get("api_key_env", "LLM_API_KEY")

    os.makedirs(args.output_dir, exist_ok=True)

    mtl_index = _index_by_chapter(args.mtl_dir)
    orig_index = _index_by_chapter(args.original_dir)

    # Load glossary
    glossary = None
    canonical = []
    if args.glossary and os.path.exists(args.glossary):
        with open(args.glossary, "r") as f:
            glossary = json.load(f)
        canonical = [e["canonical"] for e in glossary if "canonical" in e]

    # Build exemplar index
    ref_chapters = _read_text_chapters(args.original_dir)
    ref_nums = sorted(orig_index.keys())
    from translator_memory_engine.style.exemplars import build_exemplar_index

    embed_fn = None
    try:
        from fastembed import TextEmbedding

        _emb_model = TextEmbedding(model_name="BAAI/bge-base-en-v1.5")

        def _embed_fn(text: str) -> list:
            return list(_emb_model.embed([text]))[0].tolist()

        embed_fn = _embed_fn
    except ImportError:
        print("WARNING: fastembed not available, conditions C/D will use Jaccard fallback")

    exemplar_index = build_exemplar_index(
        [orig_index[n] for n in ref_nums if n in orig_index],
        ref_nums,
        embed_fn=embed_fn,
    )

    # Build style profile for condition B
    from translator_memory_engine.memory.style_bank import build_style_bank

    raw_profile = build_style_bank(ref_chapters)
    stats_line = raw_profile[-1] if raw_profile and raw_profile[-1].startswith("Measured") else None
    bank_excerpts = [e for e in raw_profile if e != stats_line]
    style_profile_b = bank_excerpts[:15]
    if stats_line:
        style_profile_b.append(stats_line)

    # Extract tendencies for condition D (from ch001 paired data)
    tendencies: Dict[str, str] = {}
    diagnostics: Dict[str, float] = {}
    if 1 in orig_index and 1 in mtl_index:
        from dotenv import load_dotenv
        from openai import OpenAI

        from translator_memory_engine.style.analyzer import (
            compute_deterministic_profile,
            extract_tendencies,
        )

        load_dotenv()
        api_key = os.environ.get(api_key_env, "")
        if api_key:
            client = OpenAI(api_key=api_key, base_url=base_url)

            def llm_fn(prompt: str) -> str:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                )
                return resp.choices[0].message.content

            tendencies = extract_tendencies(mtl_index[1], orig_index[1], llm_fn)
            diagnostics = compute_deterministic_profile(orig_index[1])
            print(f"  Extracted {len(tendencies)} tendencies from ch001")
            print(f"  Diagnostics: {list(diagnostics.keys())}")

    results = {}
    for ch_num in args.chapters:
        if ch_num not in mtl_index:
            print(f"WARNING: ch{ch_num} not found in MTL dir, skipping")
            continue
        mtl_text = mtl_index[ch_num]
        orig_text = orig_index.get(ch_num)

        print(f"\n{'=' * 60}")
        print(f"Chapter {ch_num}")
        print(f"{'=' * 60}")

        ch_results = {}

        # Condition A: Baseline
        print("  Running condition A (baseline)...")
        gen_a = run_condition_a(
            mtl_text,
            orig_text,
            args.policies,
            glossary,
            model,
            base_url,
            api_key_env,
        )
        ch_results["A"] = {
            "output": gen_a,
            "metrics": evaluate(gen_a, orig_text, mtl_text, canonical) if orig_text else {},
        }
        print(f"    cosine_delta={ch_results['A']['metrics'].get('cosine_delta', 'N/A')}")

        # Condition B: +Qualitative
        print("  Running condition B (+qualitative)...")
        gen_b = run_condition_b(
            mtl_text,
            orig_text,
            args.policies,
            glossary,
            model,
            base_url,
            api_key_env,
            style_profile_b,
        )
        ch_results["B"] = {
            "output": gen_b,
            "metrics": evaluate(gen_b, orig_text, mtl_text, canonical) if orig_text else {},
        }
        print(f"    cosine_delta={ch_results['B']['metrics'].get('cosine_delta', 'N/A')}")

        # Condition C: +Exemplars
        print("  Running condition C (+exemplars)...")
        gen_c = run_condition_c(
            mtl_text,
            orig_text,
            args.policies,
            glossary,
            model,
            base_url,
            api_key_env,
            exemplar_index,
            embed_fn,
        )
        ch_results["C"] = {
            "output": gen_c,
            "metrics": evaluate(gen_c, orig_text, mtl_text, canonical) if orig_text else {},
        }
        print(f"    cosine_delta={ch_results['C']['metrics'].get('cosine_delta', 'N/A')}")

        # Condition D: +Tendencies + Stylometry
        print("  Running condition D (+tendencies + stylometry)...")
        gen_d = run_condition_d(
            mtl_text,
            orig_text,
            args.policies,
            glossary,
            model,
            base_url,
            api_key_env,
            exemplar_index,
            embed_fn,
            tendencies,
            diagnostics,
        )
        ch_results["D"] = {
            "output": gen_d,
            "metrics": evaluate(gen_d, orig_text, mtl_text, canonical) if orig_text else {},
        }
        print(f"    cosine_delta={ch_results['D']['metrics'].get('cosine_delta', 'N/A')}")

        results[ch_num] = ch_results

        # Save outputs
        for cond, data in ch_results.items():
            out_path = os.path.join(args.output_dir, f"ch{ch_num:03d}_{cond}.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(data["output"])

    # Save metrics summary
    summary_path = os.path.join(args.output_dir, "experiment_summary.json")
    summary = {}
    for ch_num, ch_results in results.items():
        summary[ch_num] = {}
        for cond, data in ch_results.items():
            m = data["metrics"]
            summary[ch_num][cond] = {
                "cosine_delta": m.get("cosine_delta"),
                "cosine_norm_delta": round(m.get("cosine_norm_gen_orig", 0) - m.get("cosine_norm_mtl_orig", 0), 4)
                if m.get("cosine_norm_gen_orig") is not None
                else None,
                "novel_persons": m.get("faith", {}).get("novel_person_count", 0),
                "intrusion": m.get("faith", {}).get("intrusion_score", 0),
                "voice_richness_gen": m.get("voice_richness_gen"),
                "voice_richness_orig": m.get("voice_richness_orig"),
            }

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary written to: {summary_path}")

    # Print comparison table
    print(f"\n{'=' * 80}")
    print("COMPARISON TABLE")
    print(f"{'=' * 80}")
    print(f"{'Ch':>4} {'Cond':>5} {'CosΔ':>8} {'NormΔ':>8} {'NovelP':>7} {'Intr':>6} {'VR_gen':>7} {'VR_orig':>7}")
    print("-" * 80)
    for ch_num in sorted(results.keys()):
        for cond in ["A", "B", "C", "D"]:
            m = results[ch_num][cond]["metrics"]
            cos_d = m.get("cosine_delta", "N/A")
            norm_d = "-"
            if m.get("cosine_norm_gen_orig") is not None:
                norm_d = f"{m['cosine_norm_gen_orig'] - m.get('cosine_norm_mtl_orig', 0):+.4f}"
            novel = m.get("faith", {}).get("novel_person_count", "N/A")
            intr = m.get("faith", {}).get("intrusion_score", "N/A")
            vr_gen = m.get("voice_richness_gen", "N/A")
            vr_orig = m.get("voice_richness_orig", "N/A")
            cos_str = f"{cos_d:+.4f}" if isinstance(cos_d, float) else cos_d
            print(f"{ch_num:>4} {cond:>5} {cos_str:>8} {norm_d:>8} {novel:>7} {intr:>6} {vr_gen:>7} {vr_orig:>7}")


if __name__ == "__main__":
    main()
