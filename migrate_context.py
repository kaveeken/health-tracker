#!/usr/bin/env python3
"""Migration script to add context column to all entry tables."""

import sqlite3
from pathlib import Path


def migrate(db_path: Path):
    """Add context TEXT column to all entry tables."""
    conn = sqlite3.connect(db_path)

    tables = [
        "exercises",
        "heart_rate",
        "hrv",
        "temperature",
        "bodyweight",
        "control_pause",
    ]

    for table in tables:
        # Check if column already exists
        cursor = conn.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]

        if "context" not in columns:
            print(f"Adding context column to {table}...")
            conn.execute(f"ALTER TABLE {table} ADD COLUMN context TEXT")
        else:
            print(f"context column already exists in {table}")

    conn.commit()
    conn.close()
    print("Migration complete!")


if __name__ == "__main__":
    db_path = Path(__file__).parent / "health_tracker.db"
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        exit(1)
    migrate(db_path)
