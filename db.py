"""Database operations for health tracker."""

import json
import random
import sqlite3
import string
from datetime import datetime
from pathlib import Path
from typing import Optional

from parser import (
    ParsedEntry,
    ParsedExercise,
    ParsedHeartRate,
    ParsedHRV,
    ParsedTemperature,
    ParsedBodyweight,
    get_entry_type,
)


class Database:
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path(__file__).parent / "health_tracker.db"
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self):
        """Create tables if they don't exist."""
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            with open(schema_path) as f:
                schema = f.read()
            with self._connect() as conn:
                conn.executescript(schema)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _generate_hash(self, conn: sqlite3.Connection) -> str:
        """Generate a unique 4-character hash."""
        chars = string.ascii_lowercase + string.digits
        for _ in range(100):  # max attempts
            hash_code = ''.join(random.choices(chars, k=4))
            cursor = conn.execute(
                "SELECT 1 FROM raw_entries WHERE hash = ?", (hash_code,)
            )
            if cursor.fetchone() is None:
                return hash_code
        raise RuntimeError("Could not generate unique hash")

    def create_entry(self, raw_text: str, parsed: ParsedEntry) -> str:
        """Create a new entry, return its hash."""
        with self._connect() as conn:
            hash_code = self._generate_hash(conn)
            entry_type = get_entry_type(parsed)

            conn.execute(
                """
                INSERT INTO raw_entries
                (hash, timestamp, raw_text, original_text, parsed_json, entry_type)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    hash_code,
                    parsed.timestamp.isoformat(),
                    raw_text,
                    raw_text,
                    json.dumps(parsed.to_dict()),
                    entry_type,
                )
            )

            entry_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            self._insert_typed_entry(conn, entry_id, parsed)
            conn.commit()

        return hash_code

    def update_entry(self, hash_code: str, raw_text: str, parsed: ParsedEntry) -> bool:
        """Update an existing entry (correction). Return True if found and updated."""
        with self._connect() as conn:
            # Find the entry
            row = conn.execute(
                "SELECT id, entry_type FROM raw_entries WHERE hash = ? AND deleted_at IS NULL",
                (hash_code,)
            ).fetchone()

            if row is None:
                return False

            entry_id = row["id"]
            old_type = row["entry_type"]
            new_type = get_entry_type(parsed)

            # Update raw_entries
            conn.execute(
                """
                UPDATE raw_entries
                SET raw_text = ?, parsed_json = ?, entry_type = ?, timestamp = ?, parse_error = NULL
                WHERE id = ?
                """,
                (
                    raw_text,
                    json.dumps(parsed.to_dict()),
                    new_type,
                    parsed.timestamp.isoformat(),
                    entry_id,
                )
            )

            # Delete old typed entry
            self._delete_typed_entry(conn, entry_id, old_type)

            # Insert new typed entry
            self._insert_typed_entry(conn, entry_id, parsed)

            conn.commit()

        return True

    def delete_entry(self, hash_code: str) -> Optional[dict]:
        """Soft delete an entry by hash. Return entry info if found, None otherwise."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, hash, parsed_json, entry_type
                FROM raw_entries
                WHERE hash = ? AND deleted_at IS NULL
                """,
                (hash_code,)
            ).fetchone()

            if row is None:
                return None

            conn.execute(
                "UPDATE raw_entries SET deleted_at = ? WHERE id = ?",
                (datetime.now().isoformat(), row["id"])
            )
            conn.commit()

            return {
                "hash": row["hash"],
                "entry_type": row["entry_type"],
                "parsed": json.loads(row["parsed_json"]) if row["parsed_json"] else None,
            }

    def delete_last_entry(self) -> Optional[dict]:
        """Soft delete the most recent non-deleted entry. Return entry info if found."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, hash, parsed_json, entry_type
                FROM raw_entries
                WHERE deleted_at IS NULL
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()

            if row is None:
                return None

            conn.execute(
                "UPDATE raw_entries SET deleted_at = ? WHERE id = ?",
                (datetime.now().isoformat(), row["id"])
            )
            conn.commit()

            return {
                "hash": row["hash"],
                "entry_type": row["entry_type"],
                "parsed": json.loads(row["parsed_json"]) if row["parsed_json"] else None,
            }

    def get_entry_by_hash(self, hash_code: str) -> Optional[dict]:
        """Get entry by hash (including deleted)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM raw_entries WHERE hash = ?", (hash_code,)
            ).fetchone()
            if row:
                return dict(row)
        return None

    def _insert_typed_entry(self, conn: sqlite3.Connection, entry_id: int, parsed: ParsedEntry):
        """Insert into the appropriate typed table."""
        match parsed:
            case ParsedExercise():
                conn.execute(
                    """
                    INSERT INTO exercises (entry_id, name, weight_kg, reps, rpe, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry_id,
                        parsed.name,
                        parsed.weight_kg,
                        json.dumps(parsed.reps),
                        parsed.rpe,
                        parsed.timestamp.isoformat(),
                    )
                )
            case ParsedHeartRate():
                conn.execute(
                    """
                    INSERT INTO heart_rate (entry_id, bpm, context, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (entry_id, parsed.bpm, parsed.context, parsed.timestamp.isoformat())
                )
            case ParsedHRV():
                conn.execute(
                    """
                    INSERT INTO hrv (entry_id, ms, metric, context, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        entry_id,
                        parsed.ms,
                        parsed.metric,
                        parsed.context,
                        parsed.timestamp.isoformat(),
                    )
                )
            case ParsedTemperature():
                conn.execute(
                    """
                    INSERT INTO temperature (entry_id, celsius, technique, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        entry_id,
                        parsed.celsius,
                        parsed.technique,
                        parsed.timestamp.isoformat(),
                    )
                )
            case ParsedBodyweight():
                conn.execute(
                    """
                    INSERT INTO bodyweight (entry_id, kg, bodyfat_pct, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        entry_id,
                        parsed.kg,
                        parsed.bodyfat_pct,
                        parsed.timestamp.isoformat(),
                    )
                )

    def _delete_typed_entry(self, conn: sqlite3.Connection, entry_id: int, entry_type: str):
        """Delete from the appropriate typed table."""
        table_map = {
            "exercise": "exercises",
            "hr": "heart_rate",
            "hrv": "hrv",
            "temp": "temperature",
            "weight": "bodyweight",
        }
        table = table_map.get(entry_type)
        if table:
            conn.execute(f"DELETE FROM {table} WHERE entry_id = ?", (entry_id,))


def format_deleted_response(info: dict) -> str:
    """Format a deletion response message."""
    parsed = info.get("parsed")
    if not parsed:
        return f"deleted [{info['hash']}]"

    entry_type = parsed.get("type")

    if entry_type == "exercise":
        weight = f"{parsed['weight_kg']}kg" if parsed.get('weight_kg') else "(BW)"
        reps = f"[{','.join(map(str, parsed['reps']))}]"
        rpe = f" RPE {parsed['rpe']}" if parsed.get('rpe') else ""
        return f"deleted {parsed['name']} {weight} {reps}{rpe} [{info['hash']}]"

    elif entry_type == "hr":
        ctx = f" ({parsed['context']})" if parsed.get('context') else ""
        return f"deleted HR {parsed['bpm']} bpm{ctx} [{info['hash']}]"

    elif entry_type == "hrv":
        return f"deleted HRV {parsed['ms']}ms ({parsed['metric']}) [{info['hash']}]"

    elif entry_type == "temp":
        tech = f" ({parsed['technique']})" if parsed.get('technique') else ""
        return f"deleted Temp {parsed['celsius']}°C{tech} [{info['hash']}]"

    elif entry_type == "weight":
        bf = f" ({parsed['bodyfat_pct']}% BF)" if parsed.get('bodyfat_pct') else ""
        return f"deleted Weight {parsed['kg']}kg{bf} [{info['hash']}]"

    return f"deleted [{info['hash']}]"
