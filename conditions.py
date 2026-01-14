"""Conditions system for health tracker entries.

Supports multiple orthogonal condition values from different dimensions.
Each entry type can have conditions from applicable dimensions.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Dimension:
    """A dimension of conditions with valid values."""
    name: str
    priority: int  # Lower = higher priority in storage order
    values: frozenset[str]
    applies_to: frozenset[str]  # Entry types this dimension applies to


# Entry types that support conditions
ALL_CONDITION_TYPES = frozenset({"hr", "hrv", "temp", "cp"})

# Define all dimensions in priority order
# All dimensions apply to all entry types EXCEPT technique (temp-only)
DIMENSIONS = [
    Dimension(
        name="activity",
        priority=1,
        values=frozenset({"waking", "resting", "active", "post-workout"}),
        applies_to=ALL_CONDITION_TYPES,
    ),
    Dimension(
        name="time_of_day",
        priority=2,
        values=frozenset({"morning", "evening"}),
        applies_to=ALL_CONDITION_TYPES,
    ),
    Dimension(
        name="metabolic",
        priority=3,
        values=frozenset({"postprandial", "fasted"}),
        applies_to=ALL_CONDITION_TYPES,
    ),
    Dimension(
        name="emotional",
        priority=4,
        values=frozenset({"stressed", "relaxed"}),
        applies_to=ALL_CONDITION_TYPES,
    ),
    Dimension(
        name="technique",
        priority=5,
        values=frozenset({"oral", "underarm", "forehead_ir", "ear"}),
        applies_to=frozenset({"temp"}),  # Only temperature has measurement technique
    ),
]

# Build lookup structures
DIMENSION_BY_NAME = {d.name: d for d in DIMENSIONS}
VALUE_TO_DIMENSION = {}
for dim in DIMENSIONS:
    for value in dim.values:
        VALUE_TO_DIMENSION[value] = dim

# All valid condition values
ALL_VALUES = frozenset().union(*(d.values for d in DIMENSIONS))


class ConditionConflictError(ValueError):
    """Raised when multiple values from the same dimension are provided."""
    def __init__(self, dimension: str, values: list[str]):
        self.dimension = dimension
        self.values = values
        super().__init__(
            f"Cannot specify both '{values[0]}' and '{values[1]}' "
            f"({dimension} dimension)"
        )


class InvalidConditionError(ValueError):
    """Raised when a condition value is not valid for the entry type."""
    def __init__(self, value: str, entry_type: str, dimension: Optional[str] = None):
        self.value = value
        self.entry_type = entry_type
        self.dimension = dimension
        if dimension:
            super().__init__(
                f"Condition '{value}' ({dimension}) does not apply to {entry_type} entries"
            )
        else:
            super().__init__(f"Unknown condition: '{value}'")


def get_applicable_dimensions(entry_type: str) -> list[Dimension]:
    """Get dimensions that apply to an entry type, in priority order."""
    return [d for d in DIMENSIONS if entry_type in d.applies_to]


def get_applicable_values(entry_type: str) -> frozenset[str]:
    """Get all valid condition values for an entry type."""
    values = set()
    for dim in get_applicable_dimensions(entry_type):
        values.update(dim.values)
    return frozenset(values)


def parse_conditions(
    tokens: list[str],
    entry_type: str,
    aliases: Optional[dict[str, str]] = None,
) -> Optional[str]:
    """Parse condition tokens into a normalized conditions string.

    Args:
        tokens: List of potential condition tokens
        entry_type: The entry type (hr, hrv, temp, cp, etc.)
        aliases: Optional alias mapping (alias -> canonical value)

    Returns:
        Comma-separated conditions string sorted by dimension priority,
        or None if no valid conditions found.

    Raises:
        ConditionConflictError: If multiple values from same dimension provided
        InvalidConditionError: If a condition doesn't apply to entry type
    """
    if aliases is None:
        aliases = {}

    applicable = get_applicable_values(entry_type)
    found: dict[str, str] = {}  # dimension_name -> value

    for token in tokens:
        # Resolve alias
        resolved = aliases.get(token, token)

        # Skip if not a known condition value
        if resolved not in ALL_VALUES:
            continue

        dim = VALUE_TO_DIMENSION[resolved]

        # Check if this dimension applies to the entry type
        if entry_type not in dim.applies_to:
            raise InvalidConditionError(resolved, entry_type, dim.name)

        # Check for conflict within dimension
        if dim.name in found:
            raise ConditionConflictError(dim.name, [found[dim.name], resolved])

        found[dim.name] = resolved

    if not found:
        return None

    # Sort by dimension priority and join
    sorted_values = sorted(
        found.values(),
        key=lambda v: VALUE_TO_DIMENSION[v].priority
    )
    return ",".join(sorted_values)


def validate_conditions_string(conditions: Optional[str], entry_type: str) -> bool:
    """Validate a stored conditions string.

    Returns True if valid, raises exception if invalid.
    """
    if conditions is None:
        return True

    values = conditions.split(",")
    seen_dimensions: set[str] = set()

    for value in values:
        if value not in ALL_VALUES:
            raise InvalidConditionError(value, entry_type)

        dim = VALUE_TO_DIMENSION[value]

        if entry_type not in dim.applies_to:
            raise InvalidConditionError(value, entry_type, dim.name)

        if dim.name in seen_dimensions:
            raise ConditionConflictError(dim.name, [value, value])

        seen_dimensions.add(dim.name)

    return True


def format_conditions(conditions: Optional[str]) -> str:
    """Format conditions for display.

    Returns formatted string like "(resting, postprandial)" or empty string.
    """
    if not conditions:
        return ""
    return f"({conditions.replace(',', ', ')})"
