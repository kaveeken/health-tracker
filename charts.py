"""Chart generation utilities for health tracker.

This module provides reusable chart generation functions for metrics,
exercises, and trends. Designed to be imported by Claude CLI when
handling user queries.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def metric_trend(
    db_path: Path,
    metric_type: str,
    days: int = 30,
    context: Optional[str] = None,
    show_all_contexts: bool = False,
    save_path: Path = Path("/tmp/chart.png"),
) -> Path:
    """Plot time-series trend for a health metric.

    Args:
        db_path: Path to SQLite database
        metric_type: One of 'hr', 'hrv', 'temp', 'cp'
        days: Number of days to include (default 30)
        context: Filter to specific context (e.g., 'morning', 'evening')
        show_all_contexts: Plot each context as separate series with legend
        save_path: Where to save the chart (default /tmp/chart.png)

    Returns:
        Path to saved chart file

    Example:
        # Single series, all data
        metric_trend(db_path, 'hrv', days=30)

        # Filter to morning context only
        metric_trend(db_path, 'cp', days=30, context='morning')

        # Plot all contexts as separate lines
        metric_trend(db_path, 'hrv', days=30, show_all_contexts=True)
    """
    # Map metric types to table names and value columns
    metric_config = {
        'hr': ('heart_rate', 'bpm', 'Heart Rate (bpm)'),
        'hrv': ('hrv', 'ms', 'HRV (ms)'),
        'temp': ('temperature', 'celsius', 'Temperature (°C)'),
        'cp': ('control_pause', 'seconds', 'Control Pause (seconds)'),
    }

    if metric_type not in metric_config:
        raise ValueError(f"Invalid metric_type: {metric_type}. Must be one of {list(metric_config.keys())}")

    table, value_col, ylabel = metric_config[metric_type]

    # Build query
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

    base_query = f"""
        SELECT m.timestamp, m.{value_col}, m.context
        FROM {table} m
        JOIN raw_entries r ON m.entry_id = r.id
        WHERE r.deleted_at IS NULL
          AND m.timestamp >= ?
    """

    params = [cutoff_date]

    if context and not show_all_contexts:
        base_query += " AND m.context = ?"
        params.append(context)

    base_query += " ORDER BY m.timestamp"

    # Execute query
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(base_query, params)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        raise ValueError(f"No data found for {metric_type} in the last {days} days")

    # Parse data
    timestamps = [datetime.fromisoformat(row['timestamp']) for row in rows]
    values = [row[value_col] for row in rows]
    contexts = [row['context'] for row in rows]

    # Create plot
    plt.style.use('seaborn-v0_8-darkgrid')
    fig, ax = plt.subplots(figsize=(10, 6))

    if show_all_contexts:
        # Group by context and plot each separately
        context_data = {}
        for ts, val, ctx in zip(timestamps, values, contexts):
            ctx_key = ctx if ctx else 'no context'
            if ctx_key not in context_data:
                context_data[ctx_key] = {'timestamps': [], 'values': []}
            context_data[ctx_key]['timestamps'].append(ts)
            context_data[ctx_key]['values'].append(val)

        # Plot each context
        for ctx_key in sorted(context_data.keys()):
            data = context_data[ctx_key]
            ax.plot(data['timestamps'], data['values'], marker='o', label=ctx_key, linewidth=2)

        ax.legend(loc='best')
    else:
        # Single series
        ax.plot(timestamps, values, marker='o', linewidth=2, markersize=6)

    # Format x-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.xticks(rotation=45, ha='right')

    # Labels and title
    ax.set_xlabel('Date')
    ax.set_ylabel(ylabel)

    title = f"{ylabel} - Last {days} Days"
    if context and not show_all_contexts:
        title += f" ({context})"
    ax.set_title(title)

    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    # Save
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()

    return save_path


def exercise_progress(
    db_path: Path,
    exercise_name: str,
    days: int = 90,
    save_path: Path = Path("/tmp/chart.png"),
) -> Path:
    """Plot exercise progress over time (weight and volume).

    Args:
        db_path: Path to SQLite database
        exercise_name: Name of exercise (will match using aliases)
        days: Number of days to include (default 90)
        save_path: Where to save the chart

    Returns:
        Path to saved chart file
    """
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

    query = """
        SELECT e.timestamp, e.weight_kg, e.reps
        FROM exercises e
        JOIN raw_entries r ON e.entry_id = r.id
        WHERE r.deleted_at IS NULL
          AND e.name = ?
          AND e.timestamp >= ?
        ORDER BY e.timestamp
    """

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(query, [exercise_name, cutoff_date])
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        raise ValueError(f"No data found for exercise '{exercise_name}' in the last {days} days")

    # Parse data
    import json
    timestamps = [datetime.fromisoformat(row['timestamp']) for row in rows]
    weights = [row['weight_kg'] if row['weight_kg'] else 0 for row in rows]
    total_reps = [sum(json.loads(row['reps'])) for row in rows]
    volumes = [w * r for w, r in zip(weights, total_reps)]

    # Create plot with dual y-axis
    plt.style.use('seaborn-v0_8-darkgrid')
    fig, ax1 = plt.subplots(figsize=(10, 6))

    # Weight on left axis
    color = 'tab:blue'
    ax1.set_xlabel('Date')
    ax1.set_ylabel('Weight (kg)', color=color)
    ax1.plot(timestamps, weights, marker='o', color=color, label='Weight', linewidth=2)
    ax1.tick_params(axis='y', labelcolor=color)

    # Volume on right axis
    ax2 = ax1.twinx()
    color = 'tab:orange'
    ax2.set_ylabel('Volume (kg×reps)', color=color)
    ax2.plot(timestamps, volumes, marker='s', color=color, label='Volume', linewidth=2, linestyle='--')
    ax2.tick_params(axis='y', labelcolor=color)

    # Format x-axis
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
    ax1.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.xticks(rotation=45, ha='right')

    # Title
    ax1.set_title(f"{exercise_name.title()} Progress - Last {days} Days")
    ax1.grid(True, alpha=0.3)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='best')

    plt.tight_layout()

    # Save
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()

    return save_path


def volume_breakdown(
    db_path: Path,
    days: int = 7,
    save_path: Path = Path("/tmp/chart.png"),
) -> Path:
    """Plot weekly training volume breakdown by exercise.

    Args:
        db_path: Path to SQLite database
        days: Number of days to include (default 7)
        save_path: Where to save the chart

    Returns:
        Path to saved chart file
    """
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

    query = """
        SELECT e.name, e.weight_kg, e.reps
        FROM exercises e
        JOIN raw_entries r ON e.entry_id = r.id
        WHERE r.deleted_at IS NULL
          AND e.timestamp >= ?
        ORDER BY e.name
    """

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(query, [cutoff_date])
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        raise ValueError(f"No exercise data found in the last {days} days")

    # Calculate volume by exercise
    import json
    from collections import defaultdict

    volume_by_exercise = defaultdict(float)
    for row in rows:
        exercise = row['name']
        weight = row['weight_kg'] if row['weight_kg'] else 0
        total_reps = sum(json.loads(row['reps']))
        volume_by_exercise[exercise] += weight * total_reps

    # Sort by volume
    exercises = sorted(volume_by_exercise.keys(), key=lambda x: volume_by_exercise[x], reverse=True)
    volumes = [volume_by_exercise[ex] for ex in exercises]

    # Create bar chart
    plt.style.use('seaborn-v0_8-darkgrid')
    fig, ax = plt.subplots(figsize=(10, 6))

    bars = ax.barh(exercises, volumes, color='steelblue')

    # Add value labels on bars
    for bar in bars:
        width = bar.get_width()
        ax.text(width, bar.get_y() + bar.get_height()/2, f'{width:.0f}',
                ha='left', va='center', fontsize=9, fontweight='bold')

    ax.set_xlabel('Volume (kg×reps)')
    ax.set_ylabel('Exercise')
    ax.set_title(f"Training Volume Breakdown - Last {days} Days")
    ax.grid(True, alpha=0.3, axis='x')

    plt.tight_layout()

    # Save
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()

    return save_path


def bodyweight_trend(
    db_path: Path,
    days: int = 90,
    save_path: Path = Path("/tmp/chart.png"),
) -> Path:
    """Plot bodyweight trend over time.

    Args:
        db_path: Path to SQLite database
        days: Number of days to include (default 90)
        save_path: Where to save the chart

    Returns:
        Path to saved chart file
    """
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

    query = """
        SELECT b.timestamp, b.kg, b.bodyfat_pct
        FROM bodyweight b
        JOIN raw_entries r ON b.entry_id = r.id
        WHERE r.deleted_at IS NULL
          AND b.timestamp >= ?
        ORDER BY b.timestamp
    """

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(query, [cutoff_date])
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        raise ValueError(f"No bodyweight data found in the last {days} days")

    # Parse data
    timestamps = [datetime.fromisoformat(row['timestamp']) for row in rows]
    weights = [row['kg'] for row in rows]
    bodyfat_pcts = [row['bodyfat_pct'] for row in rows if row['bodyfat_pct']]
    bf_timestamps = [datetime.fromisoformat(row['timestamp']) for row in rows if row['bodyfat_pct']]

    # Create plot
    plt.style.use('seaborn-v0_8-darkgrid')
    fig, ax1 = plt.subplots(figsize=(10, 6))

    # Weight on left axis
    color = 'tab:blue'
    ax1.set_xlabel('Date')
    ax1.set_ylabel('Weight (kg)', color=color)
    ax1.plot(timestamps, weights, marker='o', color=color, linewidth=2, markersize=6)
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.grid(True, alpha=0.3)

    # Bodyfat % on right axis if data exists
    if bodyfat_pcts:
        ax2 = ax1.twinx()
        color = 'tab:orange'
        ax2.set_ylabel('Body Fat %', color=color)
        ax2.plot(bf_timestamps, bodyfat_pcts, marker='s', color=color, linewidth=2, markersize=6, linestyle='--')
        ax2.tick_params(axis='y', labelcolor=color)

    # Format x-axis
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
    ax1.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.xticks(rotation=45, ha='right')

    # Title
    ax1.set_title(f"Bodyweight Trend - Last {days} Days")

    plt.tight_layout()

    # Save
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()

    return save_path
