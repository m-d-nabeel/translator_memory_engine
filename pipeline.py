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
from translator_memory_engine.rewrite.rewriter import rewrite as rewrite_pass


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
        # Refined LLM review of the still-ambiguous policies: give the LLM the
        # example sentences AND related/overlapping policies so it can resolve
        # them (MERGE/KEEP/DROP/RETYPE) without a human in the loop.
        if verify_backend == "llm":
            needs_review_before = sum(
                1 for p in policies if getattr(p, "needs_review", False)
            )
            policies = verifier.review_ambiguous(
                policies,
                context_map=context_map,
                audit_path=os.path.join(output_dir, "review.jsonl"),
            )
            resolved = needs_review_before - sum(
                1 for p in policies if getattr(p, "needs_review", False)
            )
            print(f"  Refined review resolved: {resolved} ambiguous policies")

    # Count by type and applies mode
    policy_type_counts = Counter(p.type for p in policies)
    applies_counts = Counter(p.applies for p in policies)
    review_count = sum(
        1 for p in policies
        if getattr(p, "needs_review", False) and not getattr(p, "llm_rejected", False)
    )
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


def cmd_rewrite(args: argparse.Namespace) -> None:
    """Run the M1 rewrite pipeline on one MTL chapter or a directory of them."""
    config = _load_config(args.config)
    verify_cfg = config.get("extraction", {}).get("verification", {})
    os.makedirs(args.output, exist_ok=True)

    # Collect input files
    mtl_path = args.mtl_path
    if os.path.isdir(mtl_path):
        files = sorted(
            os.path.join(mtl_path, f)
            for f in os.listdir(mtl_path)
            if f.lower().endswith((".txt", ".md"))
        )
    else:
        files = [mtl_path]

    if not files:
        print(f"ERROR: No MTL files found at {mtl_path}")
        sys.exit(1)

    print(f"Rewriting {len(files)} MTL file(s) using {args.policies}")
    print(f"  LLM rewrite: {'on' if args.llm else 'off (pre-pass only)'}")

    total_trace = 0
    total_conflicts = 0
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        result = rewrite_pass(
            text,
            policies_path=args.policies,
            model=verify_cfg.get("model", "llama-3.1-8b-instant"),
            base_url=verify_cfg.get("base_url"),
            api_key_env=verify_cfg.get("api_key_env", "LLM_API_KEY"),
            do_llm=args.llm,
        )

        base = os.path.splitext(os.path.basename(path))[0]
        out_text = result["rewritten_text"]
        out_path = os.path.join(args.output, f"rewritten_{base}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(out_text)

        # Change trace sidecar (PLAN.md §11)
        trace_path = os.path.join(args.output, f"trace_{base}.json")
        with open(trace_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        total_trace += result["deterministic_count"]
        total_conflicts += len(result["conflicts"])
        print(f"  {base}: prepass_edits={result['deterministic_count']}, "
              f"prompted={result['prompted_count']}, conflicts={len(result['conflicts'])} "
              f"-> {out_path}")

    print(f"\n{'='*60}")
    print(f"M1 Rewrite Summary")
    print(f"{'='*60}")
    print(f"  Files rewritten:     {len(files)}")
    print(f"  Deterministic edits: {total_trace}")
    print(f"  Conflicts resolved:  {total_conflicts}")
    print(f"  Output:              {args.output}/")
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

    # rewrite command (M1)
    rewrite_parser = subparsers.add_parser(
        "rewrite",
        help="Rewrite an MTL chapter using mined policies (Retriever + Pre-pass + LLM)",
    )
    rewrite_parser.add_argument(
        "mtl_path",
        help="MTL chapter file or directory of chapter files (txt)",
    )
    rewrite_parser.add_argument(
        "--policies", "-p",
        default="outputs/policies.jsonl",
        help="Path to mined policies.jsonl (default: outputs/policies.jsonl)",
    )
    rewrite_parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    rewrite_parser.add_argument(
        "--output", "-o",
        default="outputs",
        help="Output directory (default: outputs/)",
    )
    rewrite_parser.add_argument(
        "--llm",
        action="store_true",
        default=False,
        help="Call the LLM to rewrite the pre-passed text (else pre-pass only)",
    )

    args = parser.parse_args()

    if args.command == "extract":
        cmd_extract(args)
    elif args.command == "rewrite":
        cmd_rewrite(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
