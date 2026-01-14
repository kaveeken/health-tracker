"""Rule-based parser for health tracker entries."""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from conditions import parse_conditions, format_conditions


@dataclass
class ParsedExercise:
    name: str
    weight_kg: Optional[float]
    reps: list[int]
    rpe: Optional[float]
    timestamp: datetime
    tags: Optional[list[str]] = None

    def format_response(self) -> str:
        weight = f"{self.weight_kg}kg" if self.weight_kg else "(BW)"
        reps = f"[{','.join(map(str, self.reps))}]"
        rpe = f" RPE {self.rpe}" if self.rpe else ""
        tags = f" @{' @'.join(self.tags)}" if self.tags else ""
        return f"{self.name} {weight} {reps}{rpe}{tags}"

    def to_dict(self) -> dict:
        return {
            "type": "exercise",
            "name": self.name,
            "weight_kg": self.weight_kg,
            "reps": self.reps,
            "rpe": self.rpe,
            "timestamp": self.timestamp.isoformat(),
            "tags": self.tags,
        }


@dataclass
class ParsedHeartRate:
    bpm: int
    conditions: Optional[str]
    timestamp: datetime
    tags: Optional[list[str]] = None

    def format_response(self) -> str:
        cond = f" {format_conditions(self.conditions)}" if self.conditions else ""
        tags = f" @{' @'.join(self.tags)}" if self.tags else ""
        return f"HR {self.bpm} bpm{cond}{tags}"

    def to_dict(self) -> dict:
        return {
            "type": "hr",
            "bpm": self.bpm,
            "conditions": self.conditions,
            "timestamp": self.timestamp.isoformat(),
            "tags": self.tags,
        }


@dataclass
class ParsedHRV:
    ms: float
    metric: str
    conditions: Optional[str]
    timestamp: datetime
    tags: Optional[list[str]] = None

    def format_response(self) -> str:
        cond = f" {format_conditions(self.conditions)}" if self.conditions else ""
        tags = f" @{' @'.join(self.tags)}" if self.tags else ""
        return f"HRV {self.ms}ms ({self.metric}){cond}{tags}"

    def to_dict(self) -> dict:
        return {
            "type": "hrv",
            "ms": self.ms,
            "metric": self.metric,
            "conditions": self.conditions,
            "timestamp": self.timestamp.isoformat(),
            "tags": self.tags,
        }


@dataclass
class ParsedTemperature:
    celsius: float
    conditions: Optional[str]
    timestamp: datetime
    tags: Optional[list[str]] = None

    def format_response(self) -> str:
        cond = f" {format_conditions(self.conditions)}" if self.conditions else ""
        tags = f" @{' @'.join(self.tags)}" if self.tags else ""
        return f"Temp {self.celsius}°C{cond}{tags}"

    def to_dict(self) -> dict:
        return {
            "type": "temp",
            "celsius": self.celsius,
            "conditions": self.conditions,
            "timestamp": self.timestamp.isoformat(),
            "tags": self.tags,
        }


@dataclass
class ParsedBodyweight:
    kg: float
    bodyfat_pct: Optional[float]
    timestamp: datetime
    tags: Optional[list[str]] = None

    def format_response(self) -> str:
        bf = f" ({self.bodyfat_pct}% BF)" if self.bodyfat_pct else ""
        tags = f" @{' @'.join(self.tags)}" if self.tags else ""
        return f"Weight {self.kg}kg{bf}{tags}"

    def to_dict(self) -> dict:
        return {
            "type": "weight",
            "kg": self.kg,
            "bodyfat_pct": self.bodyfat_pct,
            "timestamp": self.timestamp.isoformat(),
            "tags": self.tags,
        }


@dataclass
class ParsedControlPause:
    seconds: int
    conditions: Optional[str]
    timestamp: datetime
    tags: Optional[list[str]] = None

    def format_response(self) -> str:
        cond = f" {format_conditions(self.conditions)}" if self.conditions else ""
        tags = f" @{' @'.join(self.tags)}" if self.tags else ""
        return f"CP {self.seconds}s{cond}{tags}"

    def to_dict(self) -> dict:
        return {
            "type": "cp",
            "seconds": self.seconds,
            "conditions": self.conditions,
            "timestamp": self.timestamp.isoformat(),
            "tags": self.tags,
        }


ParsedEntry = ParsedExercise | ParsedHeartRate | ParsedHRV | ParsedTemperature | ParsedBodyweight | ParsedControlPause


class Parser:
    def __init__(self, aliases_path: Optional[Path] = None):
        self.aliases = self._load_aliases(aliases_path)

    def _load_aliases(self, path: Optional[Path]) -> dict:
        if path is None:
            path = Path(__file__).parent / "aliases.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return {"exercises": {}, "hrv_metrics": {}, "conditions": {}, "tags": {}}

    def parse(self, text: str, now: Optional[datetime] = None) -> ParsedEntry:
        """Parse a health tracker entry from text."""
        if now is None:
            now = datetime.now()

        text = text.strip().lower()

        # Extract timestamp if present (@time, @yesterday, @date)
        timestamp, text = self._extract_timestamp(text, now)

        # Extract @tags (after timestamp extraction)
        tags, text = self._extract_tags(text)

        # Determine entry type by first token
        tokens = text.split()
        if not tokens:
            raise ValueError("Empty input")

        first = tokens[0]

        # Health metrics have specific prefixes
        if first == "hr":
            return self._parse_heart_rate(tokens[1:], timestamp, tags)
        elif first == "hrv":
            return self._parse_hrv(tokens[1:], timestamp, tags)
        elif first == "temp":
            return self._parse_temperature(tokens[1:], timestamp, tags)
        elif first in ("weight", "bw"):
            return self._parse_bodyweight(tokens[1:], timestamp, tags)
        elif first in ("cp", "pause"):
            return self._parse_control_pause(tokens[1:], timestamp, tags)
        else:
            # Must be an exercise
            return self._parse_exercise(tokens, timestamp, tags)

    def _extract_timestamp(self, text: str, now: datetime) -> tuple[datetime, str]:
        """Extract @timestamp from text, return (timestamp, remaining_text)."""
        # Match @HH:MM, @yesterday, @YYYY-MM-DD
        patterns = [
            (r'@(\d{1,2}):(\d{2})', self._parse_time),
            (r'@yesterday', lambda m, n: n.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)),
            (r'@(\d{4}-\d{2}-\d{2})', self._parse_date),
        ]

        for pattern, handler in patterns:
            match = re.search(pattern, text)
            if match:
                timestamp = handler(match, now)
                text = text[:match.start()] + text[match.end():]
                return timestamp, text.strip()

        return now, text

    def _extract_tags(self, text: str) -> tuple[Optional[list[str]], str]:
        """Extract @tags from text, return (tags, remaining_text).

        Tags are @word patterns that don't match timestamp patterns.
        Applies alias resolution for auto-correction.
        """
        # Match @word but not timestamp patterns (@HH:MM, @YYYY-MM-DD, @yesterday)
        tag_pattern = r'@([a-zA-Z][a-zA-Z0-9_-]*)'

        tags = []
        tag_aliases = self.aliases.get("tags", {})

        for match in re.finditer(tag_pattern, text):
            raw_tag = match.group(1).lower()
            # Apply alias resolution (auto-correct typos)
            resolved_tag = tag_aliases.get(raw_tag, raw_tag)
            if resolved_tag not in tags:
                tags.append(resolved_tag)

        # Remove all @tags from text
        cleaned_text = re.sub(tag_pattern, '', text).strip()
        # Normalize whitespace
        cleaned_text = ' '.join(cleaned_text.split())

        return tags if tags else None, cleaned_text

    def _parse_time(self, match: re.Match, now: datetime) -> datetime:
        hour, minute = int(match.group(1)), int(match.group(2))
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def _parse_date(self, match: re.Match, now: datetime) -> datetime:
        return datetime.strptime(match.group(1), "%Y-%m-%d")

    def _parse_exercise(self, tokens: list[str], timestamp: datetime, tags: Optional[list[str]]) -> ParsedExercise:
        """Parse exercise: name [weight] reps [rpe]"""
        if len(tokens) < 2:
            raise ValueError("Exercise needs at least name and reps")

        # First token is exercise name
        name_raw = tokens[0]
        name = self.aliases.get("exercises", {}).get(name_raw, name_raw)

        rest = tokens[1:]
        weight_kg = None
        reps = None
        rpe = None

        i = 0
        while i < len(rest):
            token = rest[i]

            # Try to parse as weight (number optionally followed by kg)
            if weight_kg is None and reps is None:
                weight_match = re.match(r'^(\d+(?:\.\d+)?)(kg)?$', token)
                if weight_match:
                    # Could be weight or could be start of reps
                    # Look ahead: if next token is reps pattern, this is weight
                    if i + 1 < len(rest) and self._is_reps_pattern(rest[i + 1]):
                        weight_kg = float(weight_match.group(1))
                        i += 1
                        continue
                    # If this looks like reps pattern itself, parse as reps
                    if self._is_reps_pattern(token):
                        reps = self._parse_reps(token)
                        i += 1
                        continue
                    # Otherwise treat as weight
                    weight_kg = float(weight_match.group(1))
                    i += 1
                    continue

            # Try to parse as reps (NxM or comma-separated)
            if reps is None and self._is_reps_pattern(token):
                reps = self._parse_reps(token)
                i += 1
                continue

            # Try to parse as RPE
            if rpe is None:
                rpe_match = re.match(r'^(?:rpe)?(\d+(?:\.\d+)?)$', token)
                if rpe_match:
                    val = float(rpe_match.group(1))
                    if 1 <= val <= 10:
                        rpe = val
                        i += 1
                        continue

            i += 1

        if reps is None:
            raise ValueError("Could not parse reps")

        return ParsedExercise(
            name=name,
            weight_kg=weight_kg,
            reps=reps,
            rpe=rpe,
            timestamp=timestamp,
            tags=tags,
        )

    def _is_reps_pattern(self, token: str) -> bool:
        """Check if token looks like a reps pattern."""
        return bool(re.match(r'^(\d+x\d+|\d+(,\d+)*)$', token))

    def _parse_reps(self, token: str) -> list[int]:
        """Parse reps from NxM or comma-separated format."""
        # NxM format: 3x5 -> [5,5,5]
        nxm_match = re.match(r'^(\d+)x(\d+)$', token)
        if nxm_match:
            sets, reps = int(nxm_match.group(1)), int(nxm_match.group(2))
            return [reps] * sets

        # Comma-separated: 5,5,5 -> [5,5,5]
        if ',' in token:
            return [int(x) for x in token.split(',')]

        # Single number: 5 -> [5]
        return [int(token)]

    def _parse_heart_rate(self, tokens: list[str], timestamp: datetime, tags: Optional[list[str]]) -> ParsedHeartRate:
        """Parse heart rate: hr BPM [conditions...]"""
        if not tokens:
            raise ValueError("Heart rate needs BPM value")

        bpm = int(tokens[0])
        conditions = parse_conditions(
            tokens[1:],
            entry_type="hr",
            aliases=self.aliases.get("conditions", {}),
        )

        return ParsedHeartRate(bpm=bpm, conditions=conditions, timestamp=timestamp, tags=tags)

    def _parse_hrv(self, tokens: list[str], timestamp: datetime, tags: Optional[list[str]]) -> ParsedHRV:
        """Parse HRV: hrv MS [metric] [conditions...]"""
        if not tokens:
            raise ValueError("HRV needs milliseconds value")

        ms = float(tokens[0])
        metric = "rmssd"  # default
        condition_tokens = []

        for token in tokens[1:]:
            # Check if it's a metric
            if token in self.aliases.get("hrv_metrics", {}):
                metric = self.aliases["hrv_metrics"][token]
            elif token in ("rmssd", "sdnn"):
                metric = token
            else:
                # Assume it's a condition
                condition_tokens.append(token)

        conditions = parse_conditions(
            condition_tokens,
            entry_type="hrv",
            aliases=self.aliases.get("conditions", {}),
        )

        return ParsedHRV(ms=ms, metric=metric, conditions=conditions, timestamp=timestamp, tags=tags)

    def _parse_temperature(self, tokens: list[str], timestamp: datetime, tags: Optional[list[str]]) -> ParsedTemperature:
        """Parse temperature: temp CELSIUS [conditions...]"""
        if not tokens:
            raise ValueError("Temperature needs Celsius value")

        celsius = float(tokens[0])
        conditions = parse_conditions(
            tokens[1:],
            entry_type="temp",
            aliases=self.aliases.get("conditions", {}),
        )

        return ParsedTemperature(celsius=celsius, conditions=conditions, timestamp=timestamp, tags=tags)

    def _parse_bodyweight(self, tokens: list[str], timestamp: datetime, tags: Optional[list[str]]) -> ParsedBodyweight:
        """Parse bodyweight: weight/bw KG [bodyfat%]"""
        if not tokens:
            raise ValueError("Bodyweight needs kg value")

        kg = float(tokens[0])
        bodyfat_pct = None

        if len(tokens) > 1:
            # Could be "18%" or "18"
            bf_match = re.match(r'^(\d+(?:\.\d+)?)%?$', tokens[1])
            if bf_match:
                bodyfat_pct = float(bf_match.group(1))

        return ParsedBodyweight(kg=kg, bodyfat_pct=bodyfat_pct, timestamp=timestamp, tags=tags)

    def _parse_control_pause(self, tokens: list[str], timestamp: datetime, tags: Optional[list[str]]) -> ParsedControlPause:
        """Parse control pause: cp SECONDS [conditions...]"""
        if not tokens:
            raise ValueError("Control pause needs seconds value")

        # Parse seconds (with optional 's' suffix)
        seconds_match = re.match(r'^(\d+)s?$', tokens[0])
        if not seconds_match:
            raise ValueError(f"Invalid seconds value: {tokens[0]}")

        seconds = int(seconds_match.group(1))
        if seconds <= 0 or seconds >= 600:
            raise ValueError("Seconds must be between 1 and 599")

        conditions = parse_conditions(
            tokens[1:],
            entry_type="cp",
            aliases=self.aliases.get("conditions", {}),
        )

        return ParsedControlPause(seconds=seconds, conditions=conditions, timestamp=timestamp, tags=tags)


def get_entry_type(parsed: ParsedEntry) -> str:
    """Get the entry type string for database storage."""
    match parsed:
        case ParsedExercise():
            return "exercise"
        case ParsedHeartRate():
            return "hr"
        case ParsedHRV():
            return "hrv"
        case ParsedTemperature():
            return "temp"
        case ParsedBodyweight():
            return "weight"
        case ParsedControlPause():
            return "cp"
