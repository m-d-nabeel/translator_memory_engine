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
import logging
import os
import re
import sys
from collections import Counter
from typing import Dict, List, Optional

import yaml

from translator_memory_engine.extract import extract_signals
from translator_memory_engine.ingest.loader import load_corpus
from translator_memory_engine.memory.store import PolicyStore
from translator_memory_engine.policy.miner import mine_policies
from translator_memory_engine.policy.verifier import create_verifier
from translator_memory_engine.rewrite.rewriter import rewrite as rewrite_pass

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logger = logging.getLogger("tme")


def _setup_logging(verbose: bool = False) -> None:
    """Configure logging based on verbose flag."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s" if verbose else "%(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stderr)
    # Quiet noisy loggers
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)


def _load_config(path: str) -> dict:
    """Load YAML config file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _chapter_num(path: str) -> Optional[int]:
    """Extract the leading chapter number from a filename (e.g. 'chapter-001'
    or '001-chapter-1-village...' -> 1)."""
    m = re.search(r"(\d+)", os.path.basename(path))
    return int(m.group(1)) if m else None


def _read_text_chapters(directory: str) -> List[str]:
    """Read each .txt file in a directory as one chapter (for a style bank)."""
    chapters = []
    for f in sorted(os.listdir(directory)):
        if f.lower().endswith(".txt"):
            with open(os.path.join(directory, f), "r", encoding="utf-8") as fh:
                chapters.append(fh.read())
    return chapters


def _index_by_chapter(directory: str) -> Dict[int, str]:
    """Map chapter number -> full text for every .txt file in a directory."""
    index: Dict[int, str] = {}
    for f in sorted(os.listdir(directory)):
        if f.lower().endswith(".txt"):
            num = _chapter_num(f)
            if num is None:
                continue
            with open(os.path.join(directory, f), "r", encoding="utf-8") as fh:
                index[num] = fh.read()
    return index


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
        chapter_marker=ingest_cfg.get("chapter_marker", r"(?i)^\s*(chapter|ch)\.?\s*\d+"),
        strip_patterns=ingest_cfg.get("strip_patterns"),
    )

    if not chapters:
        # If chapter marker didn't match, treat each file as one chapter
        print("  No chapter markers found. Treating each file as one chapter.")
        chapters = load_corpus(
            args.corpus_dir,
            chapter_marker=r"^#\s+Chapter\s+\d+",  # Try markdown-style headers
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
    print("\nMining policies...")
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
            model=verify_cfg.get("model", "llama-3.3-70b-versatile"),
            base_url=verify_cfg.get("base_url"),
            api_key_env=verify_cfg.get("api_key_env", "LLM_API_KEY"),
        )
        # Build a context map (trigger -> example sentences) for the verification
        # backend, but ONLY for policies flagged for review (ambiguous / low
        # confidence). Obvious entities don't need their sentences sent (PLAN.md §3).
        context_map = {
            p.trigger: " | ".join(p.contexts[:3]) for p in policies if p.contexts and p.needs_review
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
            needs_review_before = sum(1 for p in policies if getattr(p, "needs_review", False))
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
        1
        for p in policies
        if getattr(p, "needs_review", False) and not getattr(p, "llm_rejected", False)
    )
    rejected_count = sum(1 for p in policies if getattr(p, "llm_rejected", False))

    for t, c in sorted(policy_type_counts.items()):
        print(f"    {t}: {c}")
    print("  Application mode:")
    for mode, c in sorted(applies_counts.items()):
        print(f"    {mode}: {c}")
    if policies:
        avg_conf = sum(p.confidence for p in policies) / len(policies)
        low_conf = sum(1 for p in policies if p.confidence < 0.6)
        print(f"  Avg confidence: {avg_conf:.3f}")
        print(f"  Low confidence (<0.6): {low_conf}")
        print(f"  Flagged for review:   {review_count}")
        print(
            f"  LLM-rejected (DROP):  {rejected_count}  (retained for review, excluded from glossary)"
        )

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
    print(f"\n{'=' * 60}")
    print("M0 Extraction Summary")
    print(f"{'=' * 60}")
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
    print(f"{'=' * 60}")


def cmd_rewrite(args: argparse.Namespace) -> None:
    """Run the M1 rewrite pipeline on one MTL chapter or a directory of them."""
    logger.info("=" * 60)
    logger.info("M1 Rewrite Pipeline")
    logger.info("=" * 60)

    config = _load_config(args.config)
    verify_cfg = config.get("extraction", {}).get("verification", {})
    os.makedirs(args.output, exist_ok=True)
    logger.debug(f"Config loaded: {args.config}")
    logger.debug(f"Output dir: {args.output}")

    # Optional published-reference dir (supervised mode). When present, chapters
    # are matched by number; chapters without an original fall back to the style
    # bank (unsupervised mode). D11: learn/apply/evaluate by availability.
    reference_index: Dict[int, str] = {}
    bank_excerpts: List[str] = []
    stats_line: Optional[str] = None
    exemplar_index = None

    if args.reference:
        if not os.path.isdir(args.reference):
            logger.error(f"Reference dir not found: {args.reference}")
            sys.exit(1)
        reference_index = _index_by_chapter(args.reference)
        logger.info(f"Reference dir: {args.reference} ({len(reference_index)} originals)")
        logger.debug(f"Reference chapters: {sorted(reference_index.keys())}")

        from translator_memory_engine.memory.style_bank import (
            build_exemplar_index_from_chapters,
            build_style_bank,
            retrieve_style_excerpts,
        )

        logger.info("Building style bank from reference chapters...")
        ref_chapters = _read_text_chapters(args.reference)
        raw_profile = build_style_bank(ref_chapters)
        stats_line = (
            raw_profile[-1] if raw_profile and raw_profile[-1].startswith("Measured") else None
        )
        bank_excerpts = [e for e in raw_profile if e != stats_line]
        logger.info(f"Style bank: {len(bank_excerpts)} excerpts")
        logger.debug(f"Stats line: {stats_line[:80] if stats_line else 'None'}")

        # Build exemplar index for embedding-based retrieval (fastembed if available)
        try:
            from fastembed import TextEmbedding

            logger.info("Loading embedding model (BAAI/bge-base-en-v1.5)...")
            _emb_model = TextEmbedding(model_name="BAAI/bge-base-en-v1.5")

            def _embed_fn(text: str) -> list:
                return list(_emb_model.embed([text]))[0].tolist()

            ref_nums = sorted(reference_index.keys())
            exemplar_index = build_exemplar_index_from_chapters(
                [reference_index[n] for n in ref_nums if n in reference_index],
                ref_nums,
                embed_fn=_embed_fn,
            )
            logger.info(
                f"Exemplar index: {len(exemplar_index.exemplars)} exemplars "
                f"(embedding-based retrieval)"
            )
        except ImportError:
            logger.warning("fastembed not available, using Jaccard fallback for exemplars")
            exemplar_index = None

    # Load glossary for entity shielding
    glossary: Optional[List[Dict]] = None
    if args.glossary and os.path.exists(args.glossary):
        with open(args.glossary, "r", encoding="utf-8") as f:
            glossary = json.load(f)
        logger.info(f"Glossary loaded: {len(glossary)} entries (entity shielding enabled)")
        logger.debug(f"Glossary entries: {[e.get('canonical', ['?'])[0] for e in glossary[:10]]}")

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
        logger.error(f"No MTL files found at {mtl_path}")
        sys.exit(1)

    logger.info(f"Found {len(files)} MTL file(s) to rewrite")
    logger.info(f"Policies: {args.policies}")
    llm_enabled = args.llm or args.reference or bank_excerpts
    logger.info(f"LLM rewrite: {'ON' if llm_enabled else 'OFF (pre-pass only)'}")
    logger.debug(f"MTL files: {[os.path.basename(f) for f in files]}")

    from translator_memory_engine.memory.style_bank import retrieve_style_excerpts

    total_trace = 0
    total_conflicts = 0
    prev_tail: Optional[str] = None

    for i, path in enumerate(files, 1):
        chapter_name = os.path.basename(path)
        logger.info(f"\n--- [{i}/{len(files)}] Processing: {chapter_name} ---")

        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        logger.debug(f"Read {len(text)} chars, {len(text.split())} words")

        num = _chapter_num(path)
        reference_text = reference_index.get(num) if num is not None else None
        logger.debug(f"Chapter number: {num}, has reference: {reference_text is not None}")

        # Per-chapter style retrieval: use ExemplarIndex if available,
        # otherwise fall back to Jaccard-based retrieval.
        chapter_style = None
        if reference_text is None and bank_excerpts:
            logger.debug("Retrieving style excerpts for unsupervised mode...")
            if exemplar_index is not None:
                chapter_style = retrieve_style_excerpts(
                    text,
                    bank_excerpts,
                    k=8,
                    exemplar_index=exemplar_index,
                    embed_fn=_embed_fn,
                )
            else:
                chapter_style = retrieve_style_excerpts(text, bank_excerpts, k=8)
            logger.debug(f"Retrieved {len(chapter_style) if chapter_style else 0} style excerpts")
            # Stats line excluded from LLM prompt — it causes "Measured style" dialogue bleed
            # (the 8B model treats the statistical summary as a dialogue line)

        mode = (
            "supervised_reference"
            if reference_text
            else ("unsupervised_stylebank" if chapter_style else "fallback")
        )
        use_llm = args.llm or (reference_text is not None) or (chapter_style is not None)
        logger.info(f"Mode: {mode}, LLM: {'ON' if use_llm else 'OFF'}")

        logger.info("Calling rewrite pipeline...")
        result = rewrite_pass(
            text,
            policies_path=args.policies,
            model=verify_cfg.get("model", "llama-3.3-70b-versatile"),
            base_url=verify_cfg.get("base_url"),
            api_key_env=verify_cfg.get("api_key_env", "LLM_API_KEY"),
            do_llm=use_llm,
            reference_text=reference_text,
            style_profile=chapter_style,
            glossary=glossary,
            previous_tail=prev_tail,
        )

        # Update previous_tail for cross-chapter context (last 2 paragraphs)
        rewritten = result["rewritten_text"]
        paras = [p.strip() for p in rewritten.split("\n\n") if p.strip()]
        prev_tail = "\n\n".join(paras[-2:]) if len(paras) >= 2 else (paras[-1] if paras else None)

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
        logger.info(
            f"Done: prepass_edits={result['deterministic_count']}, "
            f"prompted={result['prompted_count']}, conflicts={len(result['conflicts'])}"
        )
        logger.debug(f"Output: {out_path}")
        logger.debug(f"Trace: {trace_path}")

    logger.info(f"\n{'=' * 60}")
    logger.info("M1 Rewrite Summary")
    logger.info(f"{'=' * 60}")
    logger.info(f"  Files rewritten:     {len(files)}")
    logger.info(f"  Deterministic edits: {total_trace}")
    logger.info(f"  Conflicts resolved:  {total_conflicts}")
    logger.info(f"  Output:              {args.output}/")
    logger.info(f"{'=' * 60}")


def cmd_align(args: argparse.Namespace) -> None:
    """Alignment evaluation (PLAN §13, D11). Independent of extract/rewrite LLMs."""
    from translator_memory_engine.eval.align import (
        align_paired,
        align_unpaired,
        cosine_excluding,
        stylometry_delta,
        voice_richness_score,
    )
    from translator_memory_engine.eval.faith import (
        faithfulness_vs_reference,
        faithfulness_vs_source,
    )

    generated_index = _index_by_chapter(args.generated)
    original_index = _index_by_chapter(args.original) if args.original else {}
    mtl_index = _index_by_chapter(args.mtl) if args.mtl else {}

    # Style bank + canonical names for unpaired (Tier-2) proxy metrics.
    style_profile: List[str] = []
    canonical: List[str] = []
    if args.reference:
        from translator_memory_engine.memory.style_bank import build_style_bank

        style_profile = build_style_bank(_read_text_chapters(args.reference))
    if args.glossary and os.path.exists(args.glossary):
        with open(args.glossary, "r", encoding="utf-8") as f:
            glossary = json.load(f)
        canonical = [e["canonical"] for e in glossary if "canonical" in e]

    print(
        f"Aligning {len(generated_index)} generated chapters "
        f"(paired originals: {len(original_index)}, mtl: {len(mtl_index)})"
    )

    rows = []
    paired = 0
    unpaired = 0
    for num in sorted(generated_index):
        gen = generated_index[num]
        orig = original_index.get(num)
        if orig is not None:
            mtl = mtl_index.get(num, "")
            res = align_paired(gen, orig, mtl)
            res["sim_gen_orig_norm"] = round(cosine_excluding(gen, orig, canonical), 4)
            res["sim_mtl_orig_norm"] = round(cosine_excluding(mtl, orig, canonical), 4)
            res["faith"] = faithfulness_vs_reference(gen, orig)
            res["stylometry_delta"] = stylometry_delta(gen, orig)
            res["voice_richness_gen"] = voice_richness_score(gen)
            res["voice_richness_orig"] = voice_richness_score(orig)
            res["voice_richness_mtl"] = voice_richness_score(mtl) if mtl else None
            res = {"chapter": num, "tier": 1, **res}
            paired += 1
        else:
            mtl = mtl_index.get(num, "")
            res = align_unpaired(gen, style_profile, canonical)
            res["faith"] = faithfulness_vs_source(gen, mtl)
            res["voice_richness_gen"] = voice_richness_score(gen)
            res["voice_richness_mtl"] = voice_richness_score(mtl) if mtl else None
            res = {"chapter": num, "tier": 2, **res}
            unpaired += 1
        if args.judge:
            src = orig if orig is not None else mtl
            from translator_memory_engine.eval.judge import judge_chapter

            res["judge"] = judge_chapter(gen, src)
        rows.append(res)
        faith = res.get("faith", {})
        vr_gen = res.get("voice_richness_gen", 0)
        vr_orig = res.get("voice_richness_orig")
        vr_str = f"vr_gen={vr_gen:.3f}"
        if vr_orig is not None:
            vr_str += f" vr_orig={vr_orig:.3f}"
        print(
            f"  ch{num:>3} [tier{res['tier']}] novel_persons={faith.get('novel_person_count')} "
            f"intr={faith.get('intrusion_score')} drop={faith.get('drop_score')} "
            f"| {vr_str}  "
            + "  ".join(
                f"{k}={v}"
                for k, v in res.items()
                if k
                not in (
                    "chapter",
                    "tier",
                    "faith",
                    "judge",
                    "stylometry_delta",
                    "voice_richness_gen",
                    "voice_richness_orig",
                    "voice_richness_mtl",
                )
            )
        )

    # Summary
    if paired:
        avg_delta = sum(r["delta_vs_mtl"] for r in rows if r["tier"] == 1) / paired
        wins = sum(1 for r in rows if r["tier"] == 1 and r["delta_vs_mtl"] > 0)
        avg_norm_delta = (
            sum(r["sim_gen_orig_norm"] - r["sim_mtl_orig_norm"] for r in rows if r["tier"] == 1)
            / paired
        )
        avg_novel = sum(r["faith"]["novel_person_count"] for r in rows if r["tier"] == 1) / paired
        avg_vr_gen = sum(r.get("voice_richness_gen", 0) for r in rows if r["tier"] == 1) / paired
        avg_vr_orig = sum(r.get("voice_richness_orig", 0) for r in rows if r["tier"] == 1) / paired
        avg_vr_mtl = sum(r.get("voice_richness_mtl", 0) for r in rows if r["tier"] == 1) / paired
        print(
            f"\nTier-1 (paired, n={paired}): avg delta vs MTL = {avg_delta:+.4f}, "
            f"closer in {wins}/{paired}; name-norm delta = {avg_norm_delta:+.4f}; "
            f"avg novel persons = {avg_novel:.2f}"
        )
        print(
            f"  Voice richness: gen={avg_vr_gen:.3f}, orig={avg_vr_orig:.3f}, "
            f"mtl={avg_vr_mtl:.3f}, delta_gen_orig={avg_vr_gen - avg_vr_orig:+.3f}"
        )
        # Stylometry delta summary
        all_sdelta_keys: set = set()
        for r in rows:
            if r["tier"] == 1 and "stylometry_delta" in r:
                all_sdelta_keys.update(r["stylometry_delta"].keys())
        if all_sdelta_keys:
            parts = []
            for k in sorted(all_sdelta_keys):
                vals = [
                    r["stylometry_delta"].get(k, 0)
                    for r in rows
                    if r["tier"] == 1 and "stylometry_delta" in r
                ]
                avg = sum(vals) / len(vals) if vals else 0
                parts.append(f"{k}={avg:.3f}")
            print(f"  Stylometry delta: {'; '.join(parts)}")
    if unpaired:
        adh = [
            r["name_adherence"] for r in rows if r["tier"] == 2 and r["name_adherence"] is not None
        ]
        avg_adh = (sum(adh) / len(adh)) if adh else None
        avg_novel = sum(r["faith"]["novel_person_count"] for r in rows if r["tier"] == 2) / unpaired
        avg_intr = sum(r["faith"]["intrusion_score"] for r in rows if r["tier"] == 2) / unpaired
        avg_vr_gen = sum(r.get("voice_richness_gen", 0) for r in rows if r["tier"] == 2) / unpaired
        print(
            f"Tier-2 (unpaired, n={unpaired}): avg name adherence = "
            f"{avg_adh if avg_adh is None else round(avg_adh, 4)}; "
            f"avg novel persons = {avg_novel:.2f}; avg intrusion = {avg_intr:.2f}"
        )
        print(f"  Voice richness: gen={avg_vr_gen:.3f}")

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
        print(f"\nAlignment report written to: {args.report}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Translator Memory Engine — pipeline CLI",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose/debug logging (shows full pipeline flow)",
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
        "--config",
        "-c",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    extract_parser.add_argument(
        "--output",
        "-o",
        default="data/policies",
        help="Output directory (default: data/policies/)",
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
        "--policies",
        "-p",
        default="data/policies/policies.jsonl",
        help="Path to mined policies.jsonl (default: data/policies/policies.jsonl)",
    )
    rewrite_parser.add_argument(
        "--config",
        "-c",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    rewrite_parser.add_argument(
        "--output",
        "-o",
        default="data/output",
        help="Output directory (default: data/output/)",
    )
    rewrite_parser.add_argument(
        "--llm",
        action="store_true",
        default=False,
        help="Call the LLM to rewrite the pre-passed text (else pre-pass only)",
    )
    rewrite_parser.add_argument(
        "--reference",
        "-r",
        default=None,
        help="Directory of published original chapters. Chapters are matched by "
        "number; ones without an original fall back to the learned style bank "
        "(unsupervised mode). Forces the LLM on.",
    )
    rewrite_parser.add_argument(
        "--glossary",
        "-g",
        default=None,
        help="Path to glossary.json. When provided, glossary entries are shielded "
        "(replaced with placeholders) during LLM rewrite to prevent name mangling.",
    )

    # align command (M2 evaluation, D11-independent)
    align_parser = subparsers.add_parser(
        "align",
        help="Alignment evaluation: closeness of generated text to original / style bank",
    )
    align_parser.add_argument(
        "generated",
        help="Directory of generated (repaired) chapter files (.txt)",
    )
    align_parser.add_argument(
        "--original",
        "-g",
        default=None,
        help="Directory of published original chapters (Tier-1 paired eval)",
    )
    align_parser.add_argument(
        "--mtl",
        "-m",
        default=None,
        help="Directory of raw MTL chapters (benchmark vs generated)",
    )
    align_parser.add_argument(
        "--reference",
        "-r",
        default=None,
        help="Directory of good-translation chapters (builds the style bank for Tier-2)",
    )
    align_parser.add_argument(
        "--glossary",
        "-p",
        default=None,
        help="Path to glossary.json (canonical names for Tier-2 adherence)",
    )
    align_parser.add_argument(
        "--report",
        "-o",
        default=None,
        help="Write the per-chapter alignment rows as JSON to this path",
    )
    align_parser.add_argument(
        "--judge",
        action="store_true",
        default=False,
        help="Enable the independent Gemini judge (different model family) to score "
        "faithfulness/fluency 0-5 on each chapter. Off by default (costs API calls).",
    )

    args = parser.parse_args()
    _setup_logging(verbose=args.verbose)

    if args.command == "extract":
        cmd_extract(args)
    elif args.command == "rewrite":
        cmd_rewrite(args)
    elif args.command == "align":
        cmd_align(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
