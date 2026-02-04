"""
Migration: Add Long Echo preservation fields to content_cache table.

This migration adds preservation-related columns for storing:
- thumbnail_data: Binary thumbnail/screenshot data
- thumbnail_mime: MIME type of the thumbnail
- thumbnail_width/height: Dimensions for reference
- transcript_text: Transcripts for videos/podcasts
- extracted_text: Extracted text from PDFs and documents
- preservation_type: Type of preservation (youtube, pdf, screenshot)
- preserved_at: When the preservation was performed

These fields support the Long Echo philosophy of graceful degradation:
content remains accessible even when original sources disappear.
"""
import sqlite3
from pathlib import Path


def migrate(db_path: str) -> None:
    """
    Add preservation columns to content_cache table.

    Args:
        db_path: Path to the SQLite database file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Define columns to add: (name, type, default, create_index)
    columns_to_add = [
        ("thumbnail_data", "BLOB", None, False),
        ("thumbnail_mime", "VARCHAR(64)", None, False),
        ("thumbnail_width", "INTEGER", None, False),
        ("thumbnail_height", "INTEGER", None, False),
        ("transcript_text", "TEXT", None, False),
        ("extracted_text", "TEXT", None, False),
        ("preservation_type", "VARCHAR(32)", None, True),  # Indexed for filtering
        ("preserved_at", "TIMESTAMP", None, False),
    ]

    try:
        # Check if content_cache table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='content_cache'")
        if not cursor.fetchone():
            print("! content_cache table does not exist - skipping migration")
            print("  (Table will be created when database is initialized)")
            return

        # Get existing columns
        cursor.execute("PRAGMA table_info(content_cache)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        added_count = 0
        skipped_count = 0

        for col_name, col_type, col_default, create_index in columns_to_add:
            if col_name not in existing_columns:
                # Build ALTER TABLE statement
                sql = f"ALTER TABLE content_cache ADD COLUMN {col_name} {col_type}"
                if col_default is not None:
                    sql += f" DEFAULT {col_default}"

                cursor.execute(sql)
                added_count += 1
                print(f"✓ Added '{col_name}' column ({col_type})")

                # Create index if specified
                if create_index:
                    index_name = f"ix_content_cache_{col_name}"
                    cursor.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON content_cache({col_name})")
                    print(f"  ✓ Created index '{index_name}'")
            else:
                skipped_count += 1
                print(f"- '{col_name}' column already exists")

        conn.commit()

        if added_count > 0:
            print(f"\n✓ Migration completed: {added_count} columns added, {skipped_count} already existed")
        else:
            print(f"\n✓ Migration not needed: all {skipped_count} columns already exist")

    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        raise
    finally:
        conn.close()


def check_migration_status(db_path: str) -> dict:
    """
    Check which preservation columns exist in the database.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        Dict with column names as keys and boolean existence as values
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    preservation_columns = [
        "thumbnail_data", "thumbnail_mime", "thumbnail_width", "thumbnail_height",
        "transcript_text", "extracted_text", "preservation_type", "preserved_at"
    ]

    try:
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='content_cache'")
        if not cursor.fetchone():
            return {col: False for col in preservation_columns}

        cursor.execute("PRAGMA table_info(content_cache)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        return {col: col in existing_columns for col in preservation_columns}
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python add_preservation_fields.py <db_path> [--check]")
        print("\nOptions:")
        print("  --check    Only check migration status, don't apply")
        sys.exit(1)

    db_path = sys.argv[1]
    if not Path(db_path).exists():
        print(f"Error: Database file '{db_path}' not found")
        sys.exit(1)

    if "--check" in sys.argv:
        status = check_migration_status(db_path)
        print("Preservation columns status:")
        for col, exists in status.items():
            status_str = "✓" if exists else "✗"
            print(f"  {status_str} {col}")

        all_exist = all(status.values())
        if all_exist:
            print("\n✓ All preservation columns exist - migration not needed")
        else:
            missing = [col for col, exists in status.items() if not exists]
            print(f"\n! Missing columns: {', '.join(missing)}")
            print("  Run without --check to apply migration")
    else:
        migrate(db_path)
