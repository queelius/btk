"""
Migration: Add media metadata fields to bookmarks table.

This migration adds media-related columns for enhanced bookmark management:
- media_type: Type of media (video, audio, document, image)
- media_source: Platform source (youtube, spotify, arxiv, etc.)
- media_id: Platform-specific identifier
- author_name: Content creator/channel name
- author_url: URL to creator's profile/channel
- thumbnail_url: URL to thumbnail image
- published_at: Original publication date
"""
import sqlite3
from pathlib import Path


def migrate(db_path: str) -> None:
    """
    Add media metadata columns to bookmarks table.

    Args:
        db_path: Path to the SQLite database file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Define columns to add: (name, type, default, create_index)
    columns_to_add = [
        ("media_type", "VARCHAR(32)", None, False),
        ("media_source", "VARCHAR(64)", None, True),  # Indexed for filtering
        ("media_id", "VARCHAR(128)", None, False),
        ("author_name", "VARCHAR(256)", None, False),
        ("author_url", "VARCHAR(2048)", None, False),
        ("thumbnail_url", "VARCHAR(2048)", None, False),
        ("published_at", "TIMESTAMP", None, True),  # Indexed for sorting
    ]

    try:
        # Get existing columns
        cursor.execute("PRAGMA table_info(bookmarks)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        added_count = 0
        skipped_count = 0

        for col_name, col_type, col_default, create_index in columns_to_add:
            if col_name not in existing_columns:
                # Build ALTER TABLE statement
                sql = f"ALTER TABLE bookmarks ADD COLUMN {col_name} {col_type}"
                if col_default is not None:
                    sql += f" DEFAULT {col_default}"

                cursor.execute(sql)
                added_count += 1
                print(f"✓ Added '{col_name}' column ({col_type})")

                # Create index if specified
                if create_index:
                    index_name = f"ix_bookmarks_{col_name}"
                    cursor.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON bookmarks({col_name})")
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
    Check which media columns exist in the database.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        Dict with column names as keys and boolean existence as values
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    media_columns = [
        "media_type", "media_source", "media_id",
        "author_name", "author_url", "thumbnail_url", "published_at"
    ]

    try:
        cursor.execute("PRAGMA table_info(bookmarks)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        return {col: col in existing_columns for col in media_columns}
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python add_media_fields.py <db_path> [--check]")
        print("\nOptions:")
        print("  --check    Only check migration status, don't apply")
        sys.exit(1)

    db_path = sys.argv[1]
    if not Path(db_path).exists():
        print(f"Error: Database file '{db_path}' not found")
        sys.exit(1)

    if "--check" in sys.argv:
        status = check_migration_status(db_path)
        print("Media columns status:")
        for col, exists in status.items():
            status_str = "✓" if exists else "✗"
            print(f"  {status_str} {col}")

        all_exist = all(status.values())
        if all_exist:
            print("\n✓ All media columns exist - migration not needed")
        else:
            missing = [col for col, exists in status.items() if not exists]
            print(f"\n! Missing columns: {', '.join(missing)}")
            print("  Run without --check to apply migration")
    else:
        migrate(db_path)
