# Health Tracker Telegram Bot

## Summary

A Telegram bot for logging health/exercise data via natural language. Rule-based parser handles logging (fast, cheap), Claude handles queries (flexible, insightful).

## Architecture

```
┌──────────────┐     ┌─────────────────┐     ┌─────────────┐
│   Telegram   │────▶│  Bot Service    │────▶│   SQLite    │
│   (user)     │◀────│  (Python)       │◀────│             │
└──────────────┘     └────────┬────────┘     └─────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
              Rule-based           Claude Code
              Parser               (queries only)
              - new entries        - ? commands
              - corrections        - charts
              - deletions          - insights
```

## Command Syntax

| Pattern | Example | Handler |
|---------|---------|---------|
| Plain text | `squat 120 3x5` | Parser → new entry |
| `#hash ...` | `#a3f2 squat 130 3x5` | Parser → replace entry |
| `del` | `del` | Bot → delete last entry |
| `del #hash` | `del #a3f2` | Bot → delete specific entry |
| `? ...` | `? squat progress` | Claude → query/chart |

First token determines routing:
- `#` → correction
- `del` → deletion
- `?` → query (Claude)
- else → new entry

## Response Format

```
squat 120 3x5           → squat 120kg [5,5,5] ✓ [a3f2]
#a3f2 squat 130 3x5     → squat 130kg [5,5,5] ✓ [a3f2]
del                     → deleted squat 130kg [5,5,5] [a3f2]
del #a3f2               → deleted squat 130kg [5,5,5] [a3f2]
? squat progress        → [chart + insights from Claude]
```

## Data Model

### raw_entries
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| hash | TEXT | 4-char unique identifier |
| timestamp | DATETIME | When performed (default: now, or parsed from input) |
| created_at | DATETIME | When message received |
| raw_text | TEXT | Current message text |
| original_text | TEXT | First version (for learning) |
| parsed_json | TEXT | JSON of parsed interpretation |
| entry_type | TEXT | exercise/hr/hrv/temp/weight/unknown |
| parse_error | TEXT | Error message if parsing failed |
| deleted_at | DATETIME | Soft delete timestamp |

### exercises
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| entry_id | INTEGER | FK to raw_entries |
| name | TEXT | Normalized exercise name |
| weight_kg | REAL | Weight (null = bodyweight) |
| reps | TEXT | JSON array [5,5,5] |
| rpe | REAL | Rate of perceived exertion 1-10 |
| timestamp | DATETIME | When performed |

### heart_rate
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| entry_id | INTEGER | FK to raw_entries |
| bpm | INTEGER | Beats per minute |
| context | TEXT | resting/post-workout/active/stressed |
| timestamp | DATETIME | When measured |

### hrv
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| entry_id | INTEGER | FK to raw_entries |
| ms | REAL | HRV in milliseconds |
| metric | TEXT | rmssd/sdnn/other |
| context | TEXT | morning/resting/post-workout |
| timestamp | DATETIME | When measured |

### temperature
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| entry_id | INTEGER | FK to raw_entries |
| celsius | REAL | Temperature in Celsius |
| technique | TEXT | underarm/forehead_ir/oral/ear |
| timestamp | DATETIME | When measured |

### bodyweight
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| entry_id | INTEGER | FK to raw_entries |
| kg | REAL | Weight in kilograms |
| bodyfat_pct | REAL | Body fat percentage (optional) |
| timestamp | DATETIME | When measured |

## Parser Grammar

### Exercises
```
<exercise> ::= <name> [<weight>] <reps> [<rpe>] [<time>]
<name>     ::= word (lookup alias table)
<weight>   ::= number ["kg"]
<reps>     ::= number "x" number | number ("," number)*
<rpe>      ::= ["rpe"] number (1-10)
<time>     ::= "@" (time | "yesterday" | date)
```

### Metrics
```
<hr>      ::= "hr" number [context]
<hrv>     ::= "hrv" number ["rmssd"|"sdnn"] [context]
<temp>    ::= "temp" number [technique]
<weight>  ::= ("weight"|"bw") number [bodyfat "%"?]
```

## Input Examples

### Exercises
```
squat 120 3x5           → squat 120kg [5,5,5] ✓ [a3f2]
squat 120 5,5,5 8       → squat 120kg [5,5,5] RPE 8 ✓ [b7x1]
pullups 8,8,6           → pullups (BW) [8,8,6] ✓ [c9d3]
deadlift 180 1          → deadlift 180kg [1] ✓ [d2e4]
bp 80 5x5 rpe7          → bench press 80kg [5,5,5,5,5] RPE 7 ✓ [e5f6]
```

### Health Metrics
```
hr 65                   → HR 65 bpm (resting) ✓ [f8g7]
hr 145 workout          → HR 145 bpm (workout) ✓ [h1i2]
hrv 45                  → HRV 45ms (rmssd) ✓ [j3k4]
temp 36.8 underarm      → Temp 36.8°C (underarm) ✓ [n7o8]
weight 82.5             → Weight 82.5kg ✓ [r1s2]
bw 83 17                → Weight 83kg (17% BF) ✓ [v5w6]
```

### Corrections
```
#a3f2 squat 130 3x5     → squat 130kg [5,5,5] ✓ [a3f2]
#a3f2 squat 120 3x5 @yesterday → squat 120kg [5,5,5] 2026-01-09 ✓ [a3f2]
```

### Deletions
```
del                     → deleted squat 120kg [5,5,5] [a3f2]
del #a3f2               → deleted squat 120kg [5,5,5] [a3f2]
```

### Queries
```
? squat progress        → [chart] Your squat trend over last 30 days...
? weekly volume         → [chart] Total weekly volume breakdown...
? hrv last week         → [chart] HRV trend with 7-day average...
```

## Timestamp Handling

- Default: message receipt time
- Explicit: `@10:30`, `@yesterday`, `@2026-01-09`
- Parsed immediately by regex before main parse

## Design Decisions

- **Units**: kg only (no conversion logic)
- **Multi-entry**: One entry per message (simpler parsing, clear hash mapping)
- **Aliases**: Ship with defaults + user can add more via aliases.json

## File Structure

```
health-tracker/
├── PLAN.md
├── schema.sql
├── bot.py              # Main Telegram listener
├── parser.py           # Rule-based parser
├── aliases.json        # Exercise abbreviations
├── db.py               # Database operations
├── query.py            # Claude query handler
├── charts.py           # Matplotlib chart generation
├── health_tracker.db
└── health-tracker.service
```

## Dependencies

- Python 3.11+
- python-telegram-bot
- Claude Code CLI (queries only)
- matplotlib
- sqlite3 (stdlib)

## Deployment (Raspberry Pi)

1. Clone/copy project to Pi
2. Install dependencies: `pip install python-telegram-bot matplotlib`
3. Set up Telegram bot token in environment
4. Initialize database: `sqlite3 health_tracker.db < schema.sql`
5. Install systemd service
6. Start service: `systemctl start health-tracker`
