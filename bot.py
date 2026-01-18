#!/usr/bin/env python3
"""Telegram bot for health tracker."""

import json
import logging
import os
import re
import subprocess
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from parser import Parser, get_entry_type
from db import Database, format_deleted_response

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED_USERS = os.environ.get("ALLOWED_USER_IDS", "").split(",")
ALLOWED_USERS = [int(uid.strip()) for uid in ALLOWED_USERS if uid.strip()]
ALIAS_CATEGORIES = ("exercises", "hrv_metrics", "conditions", "tags")

# Initialize parser and database
parser = Parser()
db = Database()


def is_allowed(user_id: int) -> bool:
    """Check if user is allowed to use the bot."""
    if not ALLOWED_USERS:
        return True  # No whitelist = allow all (dev mode)
    return user_id in ALLOWED_USERS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("Not authorized.")
        return

    await update.message.reply_text(
        "Health Tracker Bot\n\n"
        "Log exercises: squat 120 3x5\n"
        "Log metrics: hr 65, hrv 45, temp 36.8, weight 82, cp 45\n"
        "Correct: #hash squat 130 3x5\n"
        "Delete: del or del #hash\n"
        "Query: ? squat progress\n"
        "Aliases: alias <term>"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route incoming messages to appropriate handlers."""
    if not is_allowed(update.effective_user.id):
        return

    text = update.message.text.strip()
    if not text:
        return

    # Determine message type by first token
    if text.startswith("#"):
        await handle_correction(update, text)
    elif text.lower().startswith("del"):
        await handle_delete(update, text)
    elif text.startswith("?"):
        await handle_query(update, text)
    elif text.lower().startswith("alias"):
        await handle_alias(update, text)
    elif text.lower() == "tags":
        await handle_tags(update)
    else:
        await handle_new_entry(update, text)


async def handle_new_entry(update: Update, text: str):
    """Handle new entry creation."""
    try:
        parsed = parser.parse(text)
        hash_code = db.create_entry(text, parsed)
        response = f"{parsed.format_response()} ✓ [{hash_code}]"

        # Add tag count info if tags present
        if parsed.tags:
            entry_type = get_entry_type(parsed)
            tag_counts = []
            for tag in parsed.tags:
                count = db.get_tag_count(tag, entry_type)
                tag_counts.append(f"@{tag}: {count}")
            response += f" ({', '.join(tag_counts)})"

        await update.message.reply_text(response)
    except ValueError as e:
        await update.message.reply_text(f"Parse error: {e}")
    except Exception as e:
        logger.exception("Error creating entry")
        await update.message.reply_text(f"Error: {e}")


async def handle_correction(update: Update, text: str):
    """Handle entry correction (#hash ...)."""
    # Extract hash from #xxxx
    match = re.match(r'^#([a-z0-9]{4})\s+(.+)$', text.lower())
    if not match:
        await update.message.reply_text("Invalid correction format. Use: #hash new entry text")
        return

    hash_code = match.group(1)
    new_text = match.group(2)

    try:
        parsed = parser.parse(new_text)
        if db.update_entry(hash_code, new_text, parsed):
            response = f"{parsed.format_response()} ✓ [{hash_code}]"

            # Add tag count info if tags present
            if parsed.tags:
                entry_type = get_entry_type(parsed)
                tag_counts = []
                for tag in parsed.tags:
                    count = db.get_tag_count(tag, entry_type)
                    tag_counts.append(f"@{tag}: {count}")
                response += f" ({', '.join(tag_counts)})"

            await update.message.reply_text(response)
        else:
            await update.message.reply_text(f"Entry [{hash_code}] not found")
    except ValueError as e:
        await update.message.reply_text(f"Parse error: {e}")
    except Exception as e:
        logger.exception("Error updating entry")
        await update.message.reply_text(f"Error: {e}")


async def handle_delete(update: Update, text: str):
    """Handle entry deletion (del or del #hash)."""
    text_lower = text.lower().strip()

    # Check for specific hash: del #xxxx
    match = re.match(r'^del\s+#([a-z0-9]{4})$', text_lower)
    if match:
        hash_code = match.group(1)
        info = db.delete_entry(hash_code)
        if info:
            await update.message.reply_text(format_deleted_response(info))
        else:
            await update.message.reply_text(f"Entry [{hash_code}] not found")
        return

    # Delete last entry: del
    if text_lower == "del":
        info = db.delete_last_entry()
        if info:
            await update.message.reply_text(format_deleted_response(info))
        else:
            await update.message.reply_text("No entries to delete")
        return

    await update.message.reply_text("Invalid delete format. Use: del or del #hash")


async def handle_query(update: Update, text: str):
    """Handle query (? ...)."""
    query = text[1:].strip()  # Remove leading ?
    if not query:
        await update.message.reply_text("Empty query. Use: ? your question")
        return

    await update.message.reply_text("Processing query...")

    try:
        # Build prompt for Claude Code
        db_path = db.db_path.absolute()
        prompt = f"""You are a health tracker assistant. The user has asked: "{query}"

The SQLite database is at: {db_path}

Tables:
- raw_entries: id, hash, timestamp, raw_text, entry_type, deleted_at
- exercises: entry_id, name, weight_kg, reps (JSON array), rpe, context, timestamp
- heart_rate: entry_id, bpm, conditions, context, timestamp
- hrv: entry_id, ms, metric, conditions, context, timestamp
- temperature: entry_id, celsius, conditions, context, timestamp
- bodyweight: entry_id, kg, bodyfat_pct, context, timestamp
- control_pause: entry_id, seconds, conditions, context, timestamp

The `conditions` column stores space-separated condition values from these dimensions:
- activity: waking, resting, active, post-workout
- time_of_day: morning, evening
- metabolic: postprandial, fasted
- emotional: stressed, relaxed
- technique (temp only): oral, underarm, forehead_ir, ear

To filter by condition, use: WHERE conditions LIKE '%fasted%'
Multiple conditions can be combined: "morning fasted" means both apply.

Only include non-deleted entries (WHERE deleted_at IS NULL when joining with raw_entries).

Answer the query concisely. If you need to write Python scripts, save them to /tmp/.

For charts, use the charts.py module with these functions:
- metric_trend(db_path, metric_type, days=30, context=None, show_all_contexts=False) - metric_type: 'hr', 'hrv', 'temp', 'cp'
- exercise_progress(db_path, exercise_name, days=90) - weight and volume over time
- volume_breakdown(db_path, days=7) - bar chart of volume by exercise
- bodyweight_trend(db_path) - stacked area chart of lean/fat mass. Plots ALL entries by default. Add days=N to limit.

All functions save to /tmp/chart.png by default.
Examples:
  from charts import metric_trend; metric_trend(Path('{db_path}'), 'hrv', days=30)
  from charts import bodyweight_trend; bodyweight_trend(Path('{db_path}'))  # all entries
"""
        # Run Claude Code with pre-approved permissions
        logger.info(f"Running claude query: {query[:50]}...")
        result = subprocess.run(
            [
                "claude",
                "-p", prompt,
                "--model", "sonnet",
                "--output-format", "json",
                "--allowedTools", "Bash(sqlite3:*),Bash(python:*),Bash(python3:*),Write(/tmp/*)",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=Path(__file__).parent
        )
        logger.info(f"Claude returncode: {result.returncode}")
        logger.info(f"Claude stderr: {result.stderr[:200] if result.stderr else 'none'}")

        # Parse JSON response for token usage and result
        try:
            data = json.loads(result.stdout)
            usage = data.get("usage", {})
            logger.info(
                f"Claude tokens - input: {usage.get('input_tokens', 0)}, "
                f"output: {usage.get('output_tokens', 0)}, "
                f"cache_read: {usage.get('cache_read_input_tokens', 0)}, "
                f"cache_creation: {usage.get('cache_creation_input_tokens', 0)}, "
                f"cost_usd: ${data.get('total_cost_usd', 0):.4f}"
            )
            response = data.get("result", "") or "No response"
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse Claude JSON output: {result.stdout[:200]}")
            response = result.stdout.strip() or result.stderr.strip() or "No response"

        # Check if a chart was generated
        chart_path = Path("/tmp/chart.png")
        if chart_path.exists():
            await update.message.reply_photo(photo=open(chart_path, "rb"))
            chart_path.unlink()  # Clean up

        # Send text response (truncate if too long)
        if len(response) > 4000:
            response = response[:4000] + "..."
        await update.message.reply_text(response)

    except subprocess.TimeoutExpired:
        await update.message.reply_text("Query timed out")
    except Exception as e:
        logger.exception("Error handling query")
        await update.message.reply_text(f"Query error: {e}")


async def handle_alias(update: Update, text: str):
    """Handle alias management (alias <search>, alias add, alias remove, alias list)."""
    args = text[5:].strip()  # Remove 'alias' prefix

    if not args:
        await update.message.reply_text(
            "Alias commands:\n"
            "  alias <term> - Search aliases\n"
            "  alias list [category] - List aliases\n"
            "  alias add <category> <abbrev> <name>\n"
            "  alias remove <category> <abbrev>\n\n"
            f"Categories: {', '.join(ALIAS_CATEGORIES)}"
        )
        return

    # Parse subcommand
    args_lower = args.lower()
    if args_lower.startswith("list") and (len(args_lower) == 4 or args_lower[4] == " "):
        await _alias_list(update, args[4:].strip())
    elif args_lower.startswith("add ") or args_lower == "add":
        await _alias_add(update, args[4:].strip())
    elif args_lower.startswith("remove ") or args_lower == "remove":
        await _alias_remove(update, args[7:].strip())
    else:
        # It's a search term
        await _alias_search(update, args)


async def _alias_search(update: Update, term: str):
    """Search aliases for a term."""
    term_lower = term.lower()
    results = []

    for category, aliases in parser.aliases.items():
        for abbrev, canonical in aliases.items():
            if term_lower in abbrev.lower() or term_lower in canonical.lower():
                results.append(f"{abbrev} → {canonical} ({category})")

    if results:
        await update.message.reply_text("\n".join(results))
    else:
        await update.message.reply_text(f"No aliases found for '{term}'")


async def _alias_list(update: Update, category: str):
    """List aliases, optionally filtered by category."""
    if not category:
        # Show all categories with counts
        lines = ["Alias categories:"]
        for cat in ALIAS_CATEGORIES:
            count = len(parser.aliases.get(cat, {}))
            lines.append(f"  {cat}: {count} aliases")
        lines.append(f"\nUse: alias list <category>")
        await update.message.reply_text("\n".join(lines))
        return

    category = category.lower()
    if category not in ALIAS_CATEGORIES:
        await update.message.reply_text(
            f"Invalid category '{category}'\n"
            f"Valid: {', '.join(ALIAS_CATEGORIES)}"
        )
        return

    aliases = parser.aliases.get(category, {})
    if not aliases:
        await update.message.reply_text(f"No aliases in '{category}'")
        return

    # Sort by abbreviation and format
    lines = [f"{category} aliases:"]
    for abbrev in sorted(aliases.keys()):
        lines.append(f"  {abbrev} → {aliases[abbrev]}")
    lines.append(f"\n({len(aliases)} total)")
    await update.message.reply_text("\n".join(lines))


async def _alias_add(update: Update, args: str):
    """Add a new alias."""
    parts = args.split(maxsplit=2)
    if len(parts) < 3:
        await update.message.reply_text(
            "Usage: alias add <category> <abbrev> <name>\n"
            "Example: alias add exercises bp bench press"
        )
        return

    category, abbrev, canonical = parts
    category = category.lower()
    abbrev = abbrev.lower()

    if category not in ALIAS_CATEGORIES:
        await update.message.reply_text(
            f"Invalid category '{category}'\n"
            f"Valid: {', '.join(ALIAS_CATEGORIES)}"
        )
        return

    # Load, modify, save
    aliases_path = Path(__file__).parent / "aliases.json"
    try:
        with open(aliases_path) as f:
            aliases = json.load(f)

        if abbrev in aliases.get(category, {}):
            existing = aliases[category][abbrev]
            await update.message.reply_text(
                f"Alias '{abbrev}' already exists → {existing}\n"
                "Remove it first to replace."
            )
            return

        aliases.setdefault(category, {})[abbrev] = canonical

        with open(aliases_path, "w") as f:
            json.dump(aliases, f, indent=2)
            f.write("\n")

        # Reload parser aliases
        parser.aliases = parser._load_aliases(None)

        await update.message.reply_text(f"✓ Added: {abbrev} → {canonical} ({category})")
    except Exception as e:
        logger.exception("Error adding alias")
        await update.message.reply_text(f"Error: {e}")


async def _alias_remove(update: Update, args: str):
    """Remove an alias."""
    parts = args.split()
    if len(parts) < 2:
        await update.message.reply_text(
            "Usage: alias remove <category> <abbrev>\n"
            "Example: alias remove exercises bp"
        )
        return

    category, abbrev = parts[0].lower(), parts[1].lower()

    if category not in ALIAS_CATEGORIES:
        await update.message.reply_text(
            f"Invalid category '{category}'\n"
            f"Valid: {', '.join(ALIAS_CATEGORIES)}"
        )
        return

    aliases_path = Path(__file__).parent / "aliases.json"
    try:
        with open(aliases_path) as f:
            aliases = json.load(f)

        if abbrev not in aliases.get(category, {}):
            await update.message.reply_text(f"Alias '{abbrev}' not found in {category}")
            return

        del aliases[category][abbrev]

        with open(aliases_path, "w") as f:
            json.dump(aliases, f, indent=2)
            f.write("\n")

        # Reload parser aliases
        parser.aliases = parser._load_aliases(None)

        await update.message.reply_text(f"✓ Removed: {abbrev} ({category})")
    except Exception as e:
        logger.exception("Error removing alias")
        await update.message.reply_text(f"Error: {e}")


async def handle_tags(update: Update):
    """Handle tags command - list all tags with usage stats."""
    tags = db.get_all_tags()

    if not tags:
        await update.message.reply_text("No tags yet. Use @tagname with entries to create tags.")
        return

    lines = ["Tags (by usage):"]
    for t in tags:
        lines.append(f"  @{t['tag']}: {t['use_count']} uses")

    await update.message.reply_text("\n".join(lines))


def main():
    """Start the bot."""
    if not BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN environment variable not set")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start polling
    logger.info("Starting bot...")
    if ALLOWED_USERS:
        logger.info(f"Allowed users: {ALLOWED_USERS}")
    else:
        logger.warning("No user whitelist configured - bot is open to all")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
