#!/usr/bin/env python3
"""Telegram bot for health tracker."""

import logging
import os
import re
import subprocess
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from parser import Parser
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
        "Log metrics: hr 65, hrv 45, temp 36.8, weight 82\n"
        "Correct: #hash squat 130 3x5\n"
        "Delete: del or del #hash\n"
        "Query: ? squat progress"
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
    else:
        await handle_new_entry(update, text)


async def handle_new_entry(update: Update, text: str):
    """Handle new entry creation."""
    try:
        parsed = parser.parse(text)
        hash_code = db.create_entry(text, parsed)
        response = f"{parsed.format_response()} ✓ [{hash_code}]"
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
- exercises: entry_id, name, weight_kg, reps (JSON array), rpe, timestamp
- heart_rate: entry_id, bpm, context, timestamp
- hrv: entry_id, ms, metric, context, timestamp
- temperature: entry_id, celsius, technique, timestamp
- bodyweight: entry_id, kg, bodyfat_pct, timestamp

Only include non-deleted entries (WHERE deleted_at IS NULL when joining with raw_entries).

Answer the query concisely. If a chart would help, generate one with matplotlib and save it to /tmp/chart.png, then mention the file path.
"""
        # Run Claude Code with pre-approved permissions
        result = subprocess.run(
            [
                "claude",
                "-p", prompt,
                "--allowedTools", "Bash(sqlite3*),Bash(python*),Write(/tmp/*)",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=Path(__file__).parent
        )

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
