#!/usr/bin/env python3
"""Import bodyweight measurements from CSV file.

CSV format:
    date,kg,bodyfat
    2026-01-15,90.1,19.5
    2026-01-10,89.8,

- date: YYYY-MM-DD format
- kg: weight in kilograms
- bodyfat: body fat percentage (optional, leave blank if not available)

Usage:
    python import_weight.py weights.csv
    python import_weight.py weights.csv --dry-run
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

from db import Database
from parser import ParsedBodyweight


def parse_date(date_str: str) -> datetime:
    """Parse date string to datetime."""
    date_str = date_str.strip()
    # Try common formats
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {date_str}")


def import_csv(csv_path: Path, dry_run: bool = False) -> tuple[int, int]:
    """Import measurements from CSV. Returns (success_count, error_count)."""
    db = Database()
    success = 0
    errors = 0

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)

        # Validate headers
        required = {"date", "kg"}
        if not required.issubset(set(reader.fieldnames or [])):
            print(f"Error: CSV must have columns: date, kg (and optionally: bodyfat)")
            print(f"Found columns: {reader.fieldnames}")
            return 0, 1

        for i, row in enumerate(reader, start=2):  # line 2 is first data row
            try:
                timestamp = parse_date(row["date"])
                kg = float(row["kg"])

                # Body fat is optional
                bf_str = row.get("bodyfat", "").strip()
                bodyfat = float(bf_str) if bf_str else None

                parsed = ParsedBodyweight(
                    kg=kg,
                    bodyfat_pct=bodyfat,
                    timestamp=timestamp,
                    tags=None,
                    context=None,
                )

                # Build raw text for storage
                raw_text = f"weight {kg}"
                if bodyfat:
                    raw_text += f" {bodyfat}"
                raw_text += f" @{timestamp.strftime('%Y-%m-%d')}"

                if dry_run:
                    bf_display = f", {bodyfat}% BF" if bodyfat else ""
                    print(f"  [dry-run] {timestamp.date()}: {kg}kg{bf_display}")
                else:
                    hash_code = db.create_entry(raw_text, parsed)
                    bf_display = f", {bodyfat}% BF" if bodyfat else ""
                    print(f"  ✓ [{hash_code}] {timestamp.date()}: {kg}kg{bf_display}")

                success += 1

            except Exception as e:
                print(f"  ✗ Line {i}: {e}")
                errors += 1

    return success, errors


def main():
    parser = argparse.ArgumentParser(description="Import bodyweight measurements from CSV")
    parser.add_argument("csv_file", type=Path, help="Path to CSV file")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    args = parser.parse_args()

    if not args.csv_file.exists():
        print(f"Error: File not found: {args.csv_file}")
        sys.exit(1)

    print(f"Importing from {args.csv_file}" + (" (dry run)" if args.dry_run else ""))
    print()

    success, errors = import_csv(args.csv_file, args.dry_run)

    print()
    print(f"Done: {success} imported, {errors} errors")

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
