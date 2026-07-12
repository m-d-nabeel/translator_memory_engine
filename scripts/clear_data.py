#!/usr/bin/env python3
"""
Clear Preprocessor & Generated Data Script (`clear_data.py`)

A comprehensive utility for clearing preprocessor data, AI-refined chapter texts,
extracted policies, character lore/glossary entries, processing jobs, and generated
output/export files with fine-grained command-line flags.

Examples:
  # Preview what would be cleared (dry run):
  python scripts/clear_data.py --all --dry-run

  # Clear all refined text, policies, glossary, jobs, and generated outputs without prompt:
  python scripts/clear_data.py --all --yes

  # Reset only refined text and processing jobs for Novel ID 1:
  python scripts/clear_data.py --clear-refined --clear-jobs --novel-id 1

  # Completely wipe all generated DB state and AI output files (SAFE: preserves local seed files in data/originals & data/mtl):
  python scripts/clear_data.py --reset-db --clear-all-files --yes
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# Resolve project root (`/home/.../translator-memory-engine`)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "translator_memory.db"
ROOT_DB_PATH = PROJECT_ROOT / "translator_memory.db"


def confirm_action(message: str, assume_yes: bool = False) -> bool:
    """Prompt user for confirmation unless `--yes` is specified."""
    if assume_yes:
        return True
    try:
        response = input(f"\n⚠️  {message} [y/N]: ").strip().lower()
        return response in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        return False


def get_table_count(conn: sqlite3.Connection, table_name: str, where_clause: str = "", params: tuple = ()) -> int:
    """Safely count rows in a table matching a condition."""
    cursor = conn.cursor()
    # Check if table exists
    cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    if cursor.fetchone()[0] == 0:
        return 0
    query = f"SELECT count(*) FROM {table_name} {where_clause}"
    cursor.execute(query, params)
    return cursor.fetchone()[0]


def clear_database(db_path: Path, args: argparse.Namespace) -> None:
    """Perform database clearing operations on the specified SQLite DB."""
    if not db_path.exists():
        print(f"ℹ️  Database not found at {db_path}. Skipping DB operations.")
        return

    print(f"\n📁 Inspecting database: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Build WHERE clause for novel filtering if requested
    novel_filter_ch = ""
    novel_filter_direct = ""
    novel_filter_job = ""
    params: tuple = ()

    if args.novel_id is not None:
        novel_id = args.novel_id
        novel_filter_ch = "WHERE novel_id = ?"
        novel_filter_direct = "WHERE novel_id = ?"
        novel_filter_job = "WHERE chapter_id IN (SELECT id FROM chapters WHERE novel_id = ?)"
        params = (novel_id,)
        print(f"🎯 Filtering DB operations to Novel ID: {novel_id}")

    # Track summary of actions
    actions = []

    # 1. Reset Database completely (--reset-db)
    if args.reset_db:
        if args.novel_id is not None:
            print("❌ Cannot combine --reset-db with --novel-id. Use specific --clear-* flags instead.")
            conn.close()
            return

        tables = ["processing_jobs", "style_snippets", "glossary", "policies", "chapters", "novels"]
        total_rows = 0
        for table in tables:
            total_rows += get_table_count(conn, table)

        if total_rows == 0:
            print("✨ Database tables are already completely empty.")
        else:
            print(f"🔍 Found {total_rows} total rows across all database tables.")
            if args.dry_run:
                print(f"🧪 [DRY RUN] Would delete all rows from tables: {', '.join(tables)}")
            elif confirm_action("Are you sure you want to completely WIPE ALL TABLES in the database?", args.yes):
                for table in tables:
                    cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?", (table,))
                    if cursor.fetchone()[0] > 0:
                        cursor.execute(f"DELETE FROM {table}")
                conn.commit()
                print("🧹 Successfully wiped all database tables.")
        conn.close()
        return

    # 2. Clear Refined Text & Chapter State (--clear-refined or --all or --clear-all-db-except-chapters)
    if args.clear_refined or args.all or args.clear_all_db_except_chapters:
        # Build exact query condition based on whether novel_id is specified
        if args.novel_id is not None:
            query_where = (
                "WHERE novel_id = ? AND (refined_text IS NOT NULL OR summary IS NOT NULL OR status != 'unprocessed')"
            )
        else:
            query_where = "WHERE refined_text IS NOT NULL OR summary IS NOT NULL OR status != 'unprocessed'"

        count = get_table_count(conn, "chapters", query_where, params)
        if count > 0:
            actions.append(
                ("chapters (reset refined_text, summary, status -> unprocessed)", query_where, params, count, True)
            )
        else:
            print("✓ No chapters with refined text or processed status found.")

    # 3. Clear Policies (--clear-policies or --all or --clear-all-db-except-chapters)
    if args.clear_policies or args.all or args.clear_all_db_except_chapters:
        count = get_table_count(conn, "policies", novel_filter_direct, params)
        if count > 0:
            actions.append(("policies table (extracted rules)", novel_filter_direct, params, count, False))
        else:
            print("✓ No extracted policies found.")

    # 4. Clear Glossary & Character Lore (--clear-glossary or --all or --clear-all-db-except-chapters)
    if args.clear_glossary or args.all or args.clear_all_db_except_chapters:
        count = get_table_count(conn, "glossary", novel_filter_direct, params)
        if count > 0:
            actions.append(("glossary table (character lore & terms)", novel_filter_direct, params, count, False))
        else:
            print("✓ No glossary/lore entries found.")

    # 5. Clear Processing Jobs (--clear-jobs or --all or --clear-all-db-except-chapters)
    if args.clear_jobs or args.all or args.clear_all_db_except_chapters:
        count = get_table_count(conn, "processing_jobs", novel_filter_job, params)
        if count > 0:
            actions.append(("processing_jobs table", novel_filter_job, params, count, False))
        else:
            print("✓ No processing jobs found.")

    # 6. Clear Style Snippets (--clear-snippets or --clear-all-db-except-chapters)
    if args.clear_snippets or args.clear_all_db_except_chapters:
        count = get_table_count(conn, "style_snippets", novel_filter_direct, params)
        if count > 0:
            actions.append(("style_snippets table", novel_filter_direct, params, count, False))
        else:
            print("✓ No style snippets found.")

    # 7. Clear Chapters (--clear-chapters)
    if args.clear_chapters:
        count = get_table_count(conn, "chapters", novel_filter_ch, params)
        if count > 0:
            actions.append(("chapters table (ALL chapters)", novel_filter_ch, params, count, False))
        else:
            print("✓ No chapters found.")

    # 8. Clear Novels (--clear-novels)
    if args.clear_novels:
        count = get_table_count(conn, "novels", novel_filter_direct if args.novel_id is not None else "", params)
        if count > 0:
            actions.append(
                (
                    "novels table (and cascading chapters/policies/glossary)",
                    novel_filter_direct if args.novel_id is not None else "",
                    params,
                    count,
                    False,
                )
            )
        else:
            print("✓ No novels found.")

    # Execute planned actions
    if not actions:
        print("💡 No matching database records need to be cleared.")
        conn.close()
        return

    print("\n🔍 Database records targeted for clearing:")
    for name, _, _, count, is_update in actions:
        op = "RESET" if is_update else "DELETE"
        print(f"  • {op}: {count} row(s) in {name}")

    if args.dry_run:
        print("\n🧪 [DRY RUN] Database modifications skipped.")
    elif confirm_action("Proceed with clearing the above database records?", args.yes):
        for name, where_clause, qparams, count, is_update in actions:
            if is_update:
                if args.novel_id is not None:
                    sql = "UPDATE chapters SET refined_text = NULL, summary = NULL, status = 'unprocessed', error_message = NULL, warnings = NULL, processing_time_ms = NULL WHERE novel_id = ?"
                else:
                    sql = "UPDATE chapters SET refined_text = NULL, summary = NULL, status = 'unprocessed', error_message = NULL, warnings = NULL, processing_time_ms = NULL"
                cursor.execute(sql, qparams)
            else:
                table_name = name.split()[0]
                sql = f"DELETE FROM {table_name} {where_clause}"
                cursor.execute(sql, qparams)
        conn.commit()
        print("🧹 Successfully updated/cleared targeted database records.")

    conn.close()


def clear_directory_files(dir_path: Path, pattern: str, label: str, dry_run: bool, yes: bool) -> int:
    """Clear matching files in a directory while preserving `.gitkeep`."""
    if not dir_path.exists():
        return 0

    files_to_delete = [f for f in dir_path.glob(pattern) if f.is_file() and f.name != ".gitkeep"]

    if not files_to_delete:
        print(f"✓ No files found in {label} ({dir_path.relative_to(PROJECT_ROOT)})")
        return 0

    print(f"\n🗑️  Found {len(files_to_delete)} file(s) in {label} ({dir_path.relative_to(PROJECT_ROOT)}):")
    for f in files_to_delete[:5]:
        print(f"  - {f.name} ({f.stat().st_size // 1024} KB)")
    if len(files_to_delete) > 5:
        print(f"  ... and {len(files_to_delete) - 5} more.")

    if dry_run:
        print(f"🧪 [DRY RUN] Would delete {len(files_to_delete)} file(s) from {label}.")
        return len(files_to_delete)

    if confirm_action(f"Delete {len(files_to_delete)} file(s) from {label}?", yes):
        deleted_count = 0
        for f in files_to_delete:
            try:
                f.unlink()
                deleted_count += 1
            except Exception as e:
                print(f"⚠️  Failed to delete {f}: {e}")
        print(f"🧹 Deleted {deleted_count} file(s) from {label}.")
        return deleted_count
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clear preprocessor data, AI-refined chapters, policies, lore, and generated output files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Master shortcut flags
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Clear all generated/refined database state and output files (refined_text, policies, glossary, jobs, output files, exported policy files).",
    )
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="Completely WIPE all database tables back to an empty state (including all chapters and novels).",
    )
    parser.add_argument(
        "--clear-all-db-except-chapters",
        action="store_true",
        help="Clear all database tables EXCEPT chapters and novels (clears policies, glossary, jobs, snippets, and resets refined_text).",
    )

    # Database specific flags
    db_group = parser.add_argument_group("Database Operations")
    db_group.add_argument(
        "--clear-refined",
        action="store_true",
        help="Reset refined chapter state (refined_text=NULL, summary=NULL, status='unprocessed').",
    )
    db_group.add_argument(
        "--clear-policies", action="store_true", help="Delete all extracted translation rules/policies from database."
    )
    db_group.add_argument(
        "--clear-glossary", action="store_true", help="Delete all character lore and glossary entries from database."
    )
    db_group.add_argument(
        "--clear-jobs",
        action="store_true",
        help="Delete all processing jobs (extract_policies, extract_lore, rewrite, etc.).",
    )
    db_group.add_argument("--clear-snippets", action="store_true", help="Delete all style snippets from database.")
    db_group.add_argument("--clear-chapters", action="store_true", help="Delete all chapters completely from database.")
    db_group.add_argument(
        "--clear-novels",
        action="store_true",
        help="Delete all novels completely from database (cascades to chapters, policies, glossary).",
    )
    db_group.add_argument(
        "-n", "--novel-id", type=int, default=None, help="Filter database clearing operations to a specific novel ID."
    )
    db_group.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database file (default: {DEFAULT_DB_PATH.relative_to(PROJECT_ROOT)}).",
    )
    db_group.add_argument(
        "--also-root-db",
        action="store_true",
        help="Also apply database clearing operations to 'translator_memory.db' in project root if it exists.",
    )

    # File system specific flags
    fs_group = parser.add_argument_group("File System & Preprocessor Output Operations")
    fs_group.add_argument(
        "--clear-output",
        action="store_true",
        help="Delete generated files in data/output/ (rewritten chapters, traces, logs).",
    )
    fs_group.add_argument(
        "--clear-policies-files",
        action="store_true",
        help="Delete exported files in data/policies/ (policies.jsonl, glossary.json).",
    )
    fs_group.add_argument(
        "--clear-mtl-files", action="store_true", help="Delete preprocessor/MTL text files in data/mtl/."
    )
    fs_group.add_argument(
        "--clear-originals-files",
        action="store_true",
        help="Delete preprocessor/original text files in data/originals/.",
    )
    fs_group.add_argument(
        "--clear-all-files",
        action="store_true",
        help="Delete all generated files (data/output and data/policies). SAFE: NEVER deletes local seed files (data/originals, data/mtl).",
    )

    # General options
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Preview what records or files would be cleared without modifying anything.",
    )
    parser.add_argument("-y", "--yes", action="store_true", help="Skip interactive confirmation prompts.")

    args = parser.parse_args()

    # Check if any action flag was provided
    has_db_action = any(
        [
            args.all,
            args.reset_db,
            args.clear_all_db_except_chapters,
            args.clear_refined,
            args.clear_policies,
            args.clear_glossary,
            args.clear_jobs,
            args.clear_snippets,
            args.clear_chapters,
            args.clear_novels,
        ]
    )
    has_fs_action = any(
        [
            args.all,
            args.clear_output,
            args.clear_policies_files,
            args.clear_mtl_files,
            args.clear_originals_files,
            args.clear_all_files,
        ]
    )

    if not (has_db_action or has_fs_action):
        parser.print_help()
        print("\n❌ Error: You must specify at least one action flag (e.g., --all, --clear-refined, --clear-output).")
        sys.exit(1)

    print("======================================================================")
    print("🧹 Translator Memory Engine — Data & Preprocessor Cleanup Utility")
    print("======================================================================")
    if args.dry_run:
        print("⚠️  RUNNING IN DRY-RUN MODE: No files or database records will be modified.")

    # 1. Execute DB operations
    if has_db_action:
        clear_database(args.db_path, args)
        if args.also_root_db and ROOT_DB_PATH.exists() and args.db_path.resolve() != ROOT_DB_PATH.resolve():
            clear_database(ROOT_DB_PATH, args)

    # 2. Execute FS operations
    if has_fs_action:
        print("\n----------------------------------------------------------------------")
        print("📁 File System Operations:")
        print("----------------------------------------------------------------------")
        if args.clear_output or args.all or args.clear_all_files:
            clear_directory_files(
                PROJECT_ROOT / "data" / "output", "*", "Generated Output Files (data/output)", args.dry_run, args.yes
            )

        if args.clear_policies_files or args.all or args.clear_all_files:
            clear_directory_files(
                PROJECT_ROOT / "data" / "policies",
                "*",
                "Exported Policy/Glossary Files (data/policies)",
                args.dry_run,
                args.yes,
            )

        if args.clear_mtl_files:
            clear_directory_files(
                PROJECT_ROOT / "data" / "mtl", "*", "Preprocessor MTL Files (data/mtl)", args.dry_run, args.yes
            )

        if args.clear_originals_files:
            clear_directory_files(
                PROJECT_ROOT / "data" / "originals",
                "*",
                "Preprocessor Original Files (data/originals)",
                args.dry_run,
                args.yes,
            )

    print("\n✅ Cleanup check complete.")
    print("======================================================================")


if __name__ == "__main__":
    main()
