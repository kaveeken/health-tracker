-- Health Tracker Database Schema

-- Raw entries: stores every incoming message
CREATE TABLE IF NOT EXISTS raw_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash TEXT UNIQUE NOT NULL,
    timestamp DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_text TEXT NOT NULL,
    original_text TEXT NOT NULL,
    parsed_json TEXT,
    entry_type TEXT CHECK (entry_type IN ('exercise', 'hr', 'hrv', 'temp', 'weight', 'unknown')),
    parse_error TEXT,
    deleted_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_raw_entries_hash ON raw_entries(hash);
CREATE INDEX IF NOT EXISTS idx_raw_entries_timestamp ON raw_entries(timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_entries_deleted ON raw_entries(deleted_at);

-- Exercises
CREATE TABLE IF NOT EXISTS exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES raw_entries(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    weight_kg REAL,
    reps TEXT NOT NULL,  -- JSON array e.g. [5,5,5]
    rpe REAL CHECK (rpe IS NULL OR (rpe >= 1 AND rpe <= 10)),
    timestamp DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_exercises_name ON exercises(name);
CREATE INDEX IF NOT EXISTS idx_exercises_timestamp ON exercises(timestamp);

-- Heart rate
CREATE TABLE IF NOT EXISTS heart_rate (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES raw_entries(id) ON DELETE CASCADE,
    bpm INTEGER NOT NULL CHECK (bpm > 0 AND bpm < 300),
    context TEXT CHECK (context IN ('resting', 'post-workout', 'active', 'stressed', NULL)),
    timestamp DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_heart_rate_timestamp ON heart_rate(timestamp);

-- Heart rate variability
CREATE TABLE IF NOT EXISTS hrv (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES raw_entries(id) ON DELETE CASCADE,
    ms REAL NOT NULL CHECK (ms > 0),
    metric TEXT NOT NULL DEFAULT 'rmssd' CHECK (metric IN ('rmssd', 'sdnn', 'other')),
    context TEXT CHECK (context IN ('morning', 'resting', 'post-workout', NULL)),
    timestamp DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hrv_timestamp ON hrv(timestamp);

-- Temperature
CREATE TABLE IF NOT EXISTS temperature (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES raw_entries(id) ON DELETE CASCADE,
    celsius REAL NOT NULL CHECK (celsius > 30 AND celsius < 45),
    technique TEXT CHECK (technique IN ('underarm', 'forehead_ir', 'oral', 'ear', NULL)),
    timestamp DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_temperature_timestamp ON temperature(timestamp);

-- Bodyweight
CREATE TABLE IF NOT EXISTS bodyweight (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES raw_entries(id) ON DELETE CASCADE,
    kg REAL NOT NULL CHECK (kg > 0 AND kg < 500),
    bodyfat_pct REAL CHECK (bodyfat_pct IS NULL OR (bodyfat_pct > 0 AND bodyfat_pct < 100)),
    timestamp DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bodyweight_timestamp ON bodyweight(timestamp);
