"""
Migration: Add archived and pinned fields to bookmarks table.

This migration adds two new boolean columns to the bookmarks table:
- archived: For hiding bookmarks from normal views
- pinned: For marking important bookmarks
"""
import sqlite3
from pathlib import Path


def migrate(db_path: str) -> None:
    """
    Add archived and pinned columns to bookmarks table.

    Args:
        db_path: Path to the SQLite database file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(bookmarks)")
        columns = {row[1] for row in cursor.fetchall()}

        # Add archived column if it doesn't exist
        if 'archived' not in columns:
            cursor.execute("""
                ALTER TABLE bookmarks
                ADD COLUMN archived BOOLEAN NOT NULL DEFAULT 0
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_bookmarks_archived ON bookmarks(archived)")
            print("✓ Added 'archived' column")
        else:
            print("- 'archived' column already exists")

        # Add pinned column if it doesn't exist
        if 'pinned' not in columns:
            cursor.execute("""
                ALTER TABLE bookmarks
                ADD COLUMN pinned BOOLEAN NOT NULL DEFAULT 0
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_bookmarks_pinned ON bookmarks(pinned)")
            print("✓ Added 'pinned' column")
        else:
            print("- 'pinned' column already exists")

        conn.commit()
        print("✓ Migration completed successfully")

    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python add_archived_pinned.py <db_path>")
        sys.exit(1)

    db_path = sys.argv[1]
    if not Path(db_path).exists():
        print(f"Error: Database file '{db_path}' not found")
        sys.exit(1)

    migrate(db_path)
