"""Pipeline CLI — orchestrates the Translator Memory Engine.

Usage:
    python pipeline.py extract <corpus_dir> [--config CONFIG] [--output OUTPUT_DIR]
    python pipeline.py extract <corpus_dir> --verify llm   # with LLM verification
    python pipeline.py extract <corpus_dir> --no-ner       # without spaCy NER

Runs the M0 extraction pipeline:
  1. Load corpus (txt/epub chapters)
  2. Extract signals (entities, terminology, honorifics, NER)
  3. Mine policies (aggregate → cluster → score)
  4. Verify policies (optional: LLM-based filtering)
  5. Store policies (policies.jsonl + glossary.json)
"""

import argparse
import json
import os
import sys
from collections import Counter

import yaml

from translator_memory_engine.ingest.loader import load_corpus
from translator_memory_engine.extract import extract_signals
from translator_memory_engine.policy.miner import mine_policies
from translator_memory_engine.policy.verifier import create_verifier
from translator_memory_engine.memory.store import PolicyStore


def _load_config(path: str) -> dict:
    """Load YAML config file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def cmd_extract(args: argparse.Namespace) -> None:
    """Run the extraction pipeline."""
    # Load config
    config = _load_config(args.config)
    output_dir = args.output or "outputs"
    os.makedirs(output_dir, exist_ok=True)

    # --- Step 1: Load corpus ---
    print(f"Loading corpus from: {args.corpus_dir}")
    ingest_cfg = config.get("ingest", {})
    chapters = load_corpus(
        args.corpus_dir,
        chapter_marker=ingest_cfg.get("chapter_marker", r'(?i)^\s*(chapter|ch)\.?\s*\d+'),
        strip_patterns=ingest_cfg.get("strip_patterns"),
    )

    if not chapters:
        # If chapter marker didn't match, treat each file as one chapter
        print("  No chapter markers found. Treating each file as one chapter.")
        chapters = load_corpus(
            args.corpus_dir,
            chapter_marker=r'^#\s+Chapter\s+\d+',  # Try markdown-style headers
            strip_patterns=ingest_cfg.get("strip_patterns"),
        )

    print(f"  Chapters loaded: {len(chapters)}")
    if not chapters:
        print("ERROR: No chapters loaded. Check corpus directory and chapter_marker.")
        sys.exit(1)

    # --- Step 2: Extract signals ---
    extract_cfg = config.get("extraction", {})
    source_languages = extract_cfg.get("source_languages")
    min_support = extract_cfg.get("min_support", 2)
    use_ner = not args.no_ner

    ner_label = "+ NER" if use_ner else "heuristics only"
    print(f"\nExtracting signals (min_support={min_support}, {ner_label})...")
    signals = extract_signals(
        chapters,
        min_support=min_support,
        source_languages=source_languages,
        use_ner=use_ner,
    )

    # Count by type
    type_counts = Counter(s.type for s in signals)
    print(f"  Signals extracted: {len(signals)}")
    for t, c in sorted(type_counts.items()):
        print(f"    {t}: {c}")

    # --- Step 3: Mine policies ---
    conf_cfg = extract_cfg.get("confidence", {})
    print(f"\nMining policies...")
    policies = mine_policies(
        signals,
        total_chapters=len(chapters),
        min_support=min_support,
        min_confidence=0.4,
        similarity_threshold=0.3,
        confidence_base=conf_cfg.get("base", 0.5),
        confidence_per_occurrence=conf_cfg.get("per_occurrence", 0.03),
        confidence_cap=conf_cfg.get("cap", 0.99),
    )

    print(f"  Policies mined: {len(policies)}")

    # --- Step 3b: Verify policies (optional) ---
    verify_backend = args.verify or extract_cfg.get("verification_backend", "none")
    if verify_backend != "none":
        verify_cfg = extract_cfg.get("verification", {})
        print(f"\nVerifying policies (backend={verify_backend})...")
        verifier = create_verifier(
            backend=verify_backend,
            model=verify_cfg.get("model", "llama-3.1-8b-instant"),
            base_url=verify_cfg.get("base_url"),
            api_key_env=verify_cfg.get("api_key_env", "LLM_API_KEY"),
        )
        # Build a context map (trigger -> example sentences) for the verification
        # backend, but ONLY for policies flagged for review (ambiguous / low
        # confidence). Obvious entities don't need their sentences sent (PLAN.md §3).
        context_map = {
            p.trigger: " | ".join(p.contexts[:3])
            for p in policies if p.contexts and p.needs_review
        }
        policies = verifier.verify_policies(
            policies,
            context_map=context_map,
            audit_path=os.path.join(output_dir, "verification.jsonl"),
        )
        print(f"  Policies after verification: {len(policies)}")

    # Count by type and applies mode
    policy_type_counts = Counter(p.type for p in policies)
    applies_counts = Counter(p.applies for p in policies)
    review_count = sum(1 for p in policies if getattr(p, "needs_review", False))
    rejected_count = sum(1 for p in policies if getattr(p, "llm_rejected", False))

    for t, c in sorted(policy_type_counts.items()):
        print(f"    {t}: {c}")
    print(f"  Application mode:")
    for mode, c in sorted(applies_counts.items()):
        print(f"    {mode}: {c}")
    if policies:
        avg_conf = sum(p.confidence for p in policies) / len(policies)
        low_conf = sum(1 for p in policies if p.confidence < 0.6)
        print(f"  Avg confidence: {avg_conf:.3f}")
        print(f"  Low confidence (<0.6): {low_conf}")
        print(f"  Flagged for review:   {review_count}")
        print(f"  LLM-rejected (DROP):  {rejected_count}  (retained for review, excluded from glossary)")

    # --- Step 4: Store ---
    store = PolicyStore()
    for p in policies:
        store.add(p)

    policies_path = os.path.join(output_dir, "policies.jsonl")
    glossary_path = os.path.join(output_dir, "glossary.json")

    store.save(policies_path)
    print(f"\n  Policies written to: {policies_path}")

    glossary = store.export_glossary()
    with open(glossary_path, "w", encoding="utf-8") as f:
        json.dump(glossary, f, indent=2, ensure_ascii=False)
    print(f"  Glossary written to: {glossary_path}")

    # --- Summary ---
    print(f"\n{'='*60}")
    print(f"M0 Extraction Summary")
    print(f"{'='*60}")
    print(f"  Chapters:           {len(chapters)}")
    print(f"  Signals:            {len(signals)}")
    print(f"  Policies:           {len(policies)}")
    print(f"    deterministic:    {applies_counts.get('deterministic', 0)}")
    print(f"    prompted:         {applies_counts.get('prompted', 0)}")
    print(f"    flagged_review:   {review_count}")
    print(f"    llm_rejected:     {rejected_count}")
    if policies:
        print(f"  Avg confidence:     {avg_conf:.3f}")
        print(f"  Low confidence:     {low_conf}")
    print(f"  Output:             {output_dir}/")
    print(f"{'='*60}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Translator Memory Engine — pipeline CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # extract command
    extract_parser = subparsers.add_parser(
        "extract",
        help="Extract policies from a corpus of good translations",
    )
    extract_parser.add_argument(
        "corpus_dir",
        help="Directory containing good-translation chapter files (txt/epub)",
    )
    extract_parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    extract_parser.add_argument(
        "--output", "-o",
        default="outputs",
        help="Output directory (default: outputs/)",
    )
    extract_parser.add_argument(
        "--verify",
        choices=["none", "llm"],
        default="none",
        help="Verification backend: none (default), llm (OpenAI-compatible provider)",
    )
    extract_parser.add_argument(
        "--no-ner",
        action="store_true",
        default=False,
        help="Disable spaCy NER extraction (use heuristics only)",
    )

    args = parser.parse_args()

    if args.command == "extract":
        cmd_extract(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
