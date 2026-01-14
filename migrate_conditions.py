#!/usr/bin/env python3
"""Migration script to convert context/technique to unified conditions field.

This migration:
1. Adds 'conditions' column to heart_rate, hrv, temperature, control_pause tables
2. Migrates existing context values to conditions
3. For temperature: merges technique and context into conditions string
4. Updates parsed_json in raw_entries to use new format
5. Drops old context/technique columns

Run with: python migrate_conditions.py [database_path]
Default database: health_tracker.db
"""

import json
import sqlite3
import sys
from pathlib import Path


def migrate(db_path: Path):
    """Run the migration."""
    print(f"Migrating database: {db_path}")

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Nothing to migrate - schema.sql will create tables with new structure.")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Check if migration is needed
        cursor = conn.execute("PRAGMA table_info(heart_rate)")
        columns = {row['name'] for row in cursor.fetchall()}

        if 'conditions' in columns and 'context' not in columns:
            print("Migration already applied.")
            return

        print("Starting migration...")

        # Step 1: Add conditions column to tables that need it
        tables_with_context = ['heart_rate', 'hrv', 'control_pause']
        for table in tables_with_context:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN conditions TEXT")
                print(f"  Added 'conditions' column to {table}")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    print(f"  'conditions' column already exists in {table}")
                else:
                    raise

        # Temperature needs special handling (has both technique and context)
        try:
            conn.execute("ALTER TABLE temperature ADD COLUMN conditions TEXT")
            print("  Added 'conditions' column to temperature")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("  'conditions' column already exists in temperature")
            else:
                raise

        # Step 2: Migrate existing context values
        print("\nMigrating existing data...")

        # Heart rate: context -> conditions (direct copy)
        conn.execute("""
            UPDATE heart_rate
            SET conditions = context
            WHERE context IS NOT NULL AND (conditions IS NULL OR conditions = '')
        """)
        print(f"  Migrated {conn.total_changes} heart_rate entries")

        # HRV: context -> conditions (direct copy)
        conn.execute("""
            UPDATE hrv
            SET conditions = context
            WHERE context IS NOT NULL AND (conditions IS NULL OR conditions = '')
        """)
        print(f"  Migrated {conn.total_changes} hrv entries")

        # Control pause: context -> conditions (direct copy)
        conn.execute("""
            UPDATE control_pause
            SET conditions = context
            WHERE context IS NOT NULL AND (conditions IS NULL OR conditions = '')
        """)
        print(f"  Migrated {conn.total_changes} control_pause entries")

        # Temperature: merge technique and context
        # Priority order: activity (none for temp), time_of_day (none), metabolic (postprandial), emotional (none), technique
        # So technique comes after metabolic conditions like postprandial
        cursor = conn.execute("""
            SELECT id, technique, context
            FROM temperature
            WHERE (technique IS NOT NULL OR context IS NOT NULL)
              AND (conditions IS NULL OR conditions = '')
        """)

        temp_updates = 0
        for row in cursor.fetchall():
            parts = []
            # Context (metabolic) comes before technique in priority order
            if row['context']:
                parts.append(row['context'])
            if row['technique']:
                parts.append(row['technique'])

            if parts:
                conditions = ','.join(parts)
                conn.execute(
                    "UPDATE temperature SET conditions = ? WHERE id = ?",
                    (conditions, row['id'])
                )
                temp_updates += 1

        print(f"  Migrated {temp_updates} temperature entries")

        # Step 3: Update parsed_json in raw_entries
        print("\nUpdating parsed_json in raw_entries...")

        # Process each entry type
        cursor = conn.execute("""
            SELECT id, entry_type, parsed_json
            FROM raw_entries
            WHERE parsed_json IS NOT NULL
              AND entry_type IN ('hr', 'hrv', 'temp', 'cp')
        """)

        json_updates = 0
        for row in cursor.fetchall():
            try:
                parsed = json.loads(row['parsed_json'])
            except (json.JSONDecodeError, TypeError):
                continue

            updated = False
            entry_type = row['entry_type']

            if entry_type == 'temp':
                # Merge technique and context into conditions
                parts = []
                if parsed.get('context'):
                    parts.append(parsed['context'])
                if parsed.get('technique'):
                    parts.append(parsed['technique'])

                conditions = ','.join(parts) if parts else None

                # Remove old fields, add new
                parsed.pop('context', None)
                parsed.pop('technique', None)
                parsed['conditions'] = conditions
                updated = True

            elif entry_type in ('hr', 'hrv', 'cp'):
                # Rename context to conditions
                if 'context' in parsed:
                    parsed['conditions'] = parsed.pop('context')
                    updated = True

            if updated:
                conn.execute(
                    "UPDATE raw_entries SET parsed_json = ? WHERE id = ?",
                    (json.dumps(parsed), row['id'])
                )
                json_updates += 1

        print(f"  Updated {json_updates} parsed_json entries")

        # Step 4: Create new tables without old columns and migrate data
        # SQLite doesn't support DROP COLUMN easily, so we recreate tables
        print("\nRecreating tables without old columns...")

        # Heart rate
        conn.execute("""
            CREATE TABLE IF NOT EXISTS heart_rate_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL REFERENCES raw_entries(id) ON DELETE CASCADE,
                bpm INTEGER NOT NULL CHECK (bpm > 0 AND bpm < 300),
                conditions TEXT,
                timestamp DATETIME NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO heart_rate_new (id, entry_id, bpm, conditions, timestamp)
            SELECT id, entry_id, bpm, conditions, timestamp FROM heart_rate
        """)
        conn.execute("DROP TABLE heart_rate")
        conn.execute("ALTER TABLE heart_rate_new RENAME TO heart_rate")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_heart_rate_timestamp ON heart_rate(timestamp)")
        print("  Recreated heart_rate table")

        # HRV
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hrv_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL REFERENCES raw_entries(id) ON DELETE CASCADE,
                ms REAL NOT NULL CHECK (ms > 0),
                metric TEXT NOT NULL DEFAULT 'rmssd' CHECK (metric IN ('rmssd', 'sdnn', 'other')),
                conditions TEXT,
                timestamp DATETIME NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO hrv_new (id, entry_id, ms, metric, conditions, timestamp)
            SELECT id, entry_id, ms, metric, conditions, timestamp FROM hrv
        """)
        conn.execute("DROP TABLE hrv")
        conn.execute("ALTER TABLE hrv_new RENAME TO hrv")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hrv_timestamp ON hrv(timestamp)")
        print("  Recreated hrv table")

        # Temperature
        conn.execute("""
            CREATE TABLE IF NOT EXISTS temperature_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL REFERENCES raw_entries(id) ON DELETE CASCADE,
                celsius REAL NOT NULL CHECK (celsius > 30 AND celsius < 45),
                conditions TEXT,
                timestamp DATETIME NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO temperature_new (id, entry_id, celsius, conditions, timestamp)
            SELECT id, entry_id, celsius, conditions, timestamp FROM temperature
        """)
        conn.execute("DROP TABLE temperature")
        conn.execute("ALTER TABLE temperature_new RENAME TO temperature")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_temperature_timestamp ON temperature(timestamp)")
        print("  Recreated temperature table")

        # Control pause
        conn.execute("""
            CREATE TABLE IF NOT EXISTS control_pause_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL REFERENCES raw_entries(id) ON DELETE CASCADE,
                seconds INTEGER NOT NULL CHECK (seconds > 0 AND seconds < 600),
                conditions TEXT,
                timestamp DATETIME NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO control_pause_new (id, entry_id, seconds, conditions, timestamp)
            SELECT id, entry_id, seconds, conditions, timestamp FROM control_pause
        """)
        conn.execute("DROP TABLE control_pause")
        conn.execute("ALTER TABLE control_pause_new RENAME TO control_pause")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_control_pause_timestamp ON control_pause(timestamp)")
        print("  Recreated control_pause table")

        conn.commit()
        print("\nMigration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"\nError during migration: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
    else:
        db_path = Path(__file__).parent / "health_tracker.db"

    migrate(db_path)
