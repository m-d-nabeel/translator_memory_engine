"""Export policies and glossary from SQLite back to JSONL/JSON files.

This is a safety-net utility for the SQLite migration. It allows you to
dump the canonical data from the database back to flat files that can be
used by the legacy CLI pipeline or as backups.

Usage:
    uv run python scripts/sqlite_to_jsonl.py [--db PATH] [--output DIR]

Defaults:
    --db      data/translator_memory.db
    --output  data/policies
"""

import argparse
import json
import os
import sqlite3
import sys


def export_policies(db_path: str, output_dir: str, novel_id: int = 1) -> int:
    """Export policies from SQLite to policies.jsonl."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT policy_id, type, trigger, match_forms, action, confidence, "
        "evidence_chapters, applies, scores, category, note, needs_review, "
        "llm_rejected, contexts "
        "FROM policies WHERE novel_id = ?",
        (novel_id,),
    )

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "policies.jsonl")
    count = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for row in cursor:
            (
                policy_id, ptype, trigger, match_json, action_json,
                confidence, evidence_json, applies, scores_json, category,
                note, needs_review, llm_rejected, contexts_json,
            ) = row
            policy = {
                "id": policy_id,
                "type": ptype,
                "trigger": trigger,
                "match": json.loads(match_json) if match_json else [],
                "action": json.loads(action_json) if action_json else {},
                "confidence": confidence,
                "evidence": json.loads(evidence_json) if evidence_json else [],
                "applies": applies or "deterministic",
            }
            if scores_json:
                policy["scores"] = json.loads(scores_json)
            if category:
                policy["category"] = category
            if note:
                policy["note"] = note
            if (needs_review or "false").lower() == "true":
                policy["needs_review"] = True
            if (llm_rejected or "false").lower() == "true":
                policy["llm_rejected"] = True
            if contexts_json:
                policy["contexts"] = json.loads(contexts_json)
            f.write(json.dumps(policy, ensure_ascii=False) + "\n")
            count += 1

    conn.close()
    print(f"Exported {count} policies to {out_path}")
    return count


def export_glossary(db_path: str, output_dir: str, novel_id: int = 1) -> int:
    """Export glossary from SQLite to glossary.json."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT canonical, aliases, entity_type, confidence "
        "FROM glossary WHERE novel_id = ?",
        (novel_id,),
    )

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "glossary.json")
    entries = []
    for row in cursor:
        canonical, aliases_json, entity_type, confidence = row
        entries.append({
            "canonical": canonical,
            "aliases": json.loads(aliases_json) if aliases_json else [],
            "type": entity_type,
            "confidence": confidence,
        })

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    conn.close()
    print(f"Exported {len(entries)} glossary entries to {out_path}")
    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export policies and glossary from SQLite to JSONL/JSON files",
    )
    parser.add_argument(
        "--db",
        default="data/translator_memory.db",
        help="Path to SQLite database (default: data/translator_memory.db)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="data/policies",
        help="Output directory (default: data/policies/)",
    )
    parser.add_argument(
        "--novel-id",
        type=int,
        default=1,
        help="Novel ID to export (default: 1)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"Error: Database not found at {args.db}", file=sys.stderr)
        sys.exit(1)

    policy_count = export_policies(args.db, args.output, args.novel_id)
    glossary_count = export_glossary(args.db, args.output, args.novel_id)

    print(f"\nExport complete: {policy_count} policies, {glossary_count} glossary entries")
    print(f"Output directory: {args.output}/")


if __name__ == "__main__":
    main()
