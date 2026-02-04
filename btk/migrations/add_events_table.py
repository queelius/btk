"""
Migration: Add events table for full audit trail.

This migration creates the events table to track all operations in BTK:
- bookmark_added, bookmark_updated, bookmark_deleted
- bookmark_visited, bookmark_starred, bookmark_unstarred
- bookmark_archived, bookmark_unarchived, bookmark_pinned
- tag_added, tag_removed, tag_renamed
- content_fetched, content_preserved
- health_checked
- queue_added, queue_removed, queue_completed
- import_completed, export_completed
"""
import sqlite3
from pathlib import Path


def migrate(db_path: str) -> None:
    """
    Create the events table for audit trail.

    Args:
        db_path: Path to the SQLite database file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='events'
        """)
        if cursor.fetchone():
            print("- Events table already exists")
            return

        # Create events table
        cursor.execute("""
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type VARCHAR(32) NOT NULL,
                entity_type VARCHAR(32) NOT NULL,
                entity_id INTEGER,
                entity_url VARCHAR(2048),
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                event_data JSON
            )
        """)
        print("✓ Created 'events' table")

        # Create indexes
        indexes = [
            ("ix_events_event_type", "event_type"),
            ("ix_events_timestamp", "timestamp"),
            ("ix_events_entity", "entity_type, entity_id"),
        ]

        for index_name, columns in indexes:
            cursor.execute(f"CREATE INDEX {index_name} ON events({columns})")
            print(f"  ✓ Created index '{index_name}'")

        conn.commit()
        print("\n✓ Migration completed: events table created with indexes")

    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        raise
    finally:
        conn.close()


def check_migration_status(db_path: str) -> dict:
    """
    Check if the events table exists.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        Dict with table existence and index status
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check table
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='events'
        """)
        table_exists = cursor.fetchone() is not None

        # Check indexes
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND tbl_name='events'
        """)
        indexes = [row[0] for row in cursor.fetchall()]

        return {
            "table_exists": table_exists,
            "indexes": indexes
        }
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python add_events_table.py <db_path> [--check]")
        print("\nOptions:")
        print("  --check    Only check migration status, don't apply")
        sys.exit(1)

    db_path = sys.argv[1]
    if not Path(db_path).exists():
        print(f"Error: Database file '{db_path}' not found")
        sys.exit(1)

    if "--check" in sys.argv:
        status = check_migration_status(db_path)
        print("Events table status:")
        status_str = "✓" if status["table_exists"] else "✗"
        print(f"  {status_str} Table exists: {status['table_exists']}")
        if status["indexes"]:
            print(f"  ✓ Indexes: {', '.join(status['indexes'])}")
        else:
            print("  ✗ No indexes found")

        if status["table_exists"]:
            print("\n✓ Migration not needed - events table exists")
        else:
            print("\n! Events table missing")
            print("  Run without --check to apply migration")
    else:
        migrate(db_path)
