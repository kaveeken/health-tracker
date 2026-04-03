"""Tests for the conditions system."""

import pytest
from conditions import (
    parse_conditions,
    validate_conditions_string,
    format_conditions,
    get_applicable_dimensions,
    get_applicable_values,
    ConditionConflictError,
    InvalidConditionError,
    DIMENSIONS,
)


class TestDimensionDefinitions:
    """Test dimension definitions are correctly structured."""

    def test_all_dimensions_have_priority(self):
        """All dimensions have a unique priority."""
        priorities = [d.priority for d in DIMENSIONS]
        assert len(priorities) == len(set(priorities))

    def test_dimensions_sorted_by_priority(self):
        """Dimensions list is sorted by priority."""
        priorities = [d.priority for d in DIMENSIONS]
        assert priorities == sorted(priorities)

    def test_activity_dimension_values(self):
        """Activity dimension has expected values."""
        from conditions import DIMENSION_BY_NAME
        activity = DIMENSION_BY_NAME["activity"]
        assert "waking" in activity.values
        assert "resting" in activity.values
        assert "active" in activity.values
        assert "post-workout" in activity.values

    def test_technique_only_applies_to_temp(self):
        """Technique dimension only applies to temperature entries."""
        from conditions import DIMENSION_BY_NAME
        technique = DIMENSION_BY_NAME["technique"]
        assert technique.applies_to == frozenset({"temp"})


class TestGetApplicableDimensions:
    """Test get_applicable_dimensions function."""

    def test_hr_applicable_dimensions(self):
        """HR entries have all dimensions except technique."""
        dims = get_applicable_dimensions("hr")
        dim_names = {d.name for d in dims}
        assert "activity" in dim_names
        assert "time_of_day" in dim_names
        assert "metabolic" in dim_names
        assert "emotional" in dim_names
        assert "technique" not in dim_names  # Only temp has technique

    def test_temp_applicable_dimensions(self):
        """Temperature entries have all dimensions including technique."""
        dims = get_applicable_dimensions("temp")
        dim_names = {d.name for d in dims}
        assert "activity" in dim_names
        assert "time_of_day" in dim_names
        assert "metabolic" in dim_names
        assert "emotional" in dim_names
        assert "technique" in dim_names  # Temp is the only one with technique

    def test_cp_applicable_dimensions(self):
        """Control pause entries have all dimensions except technique."""
        dims = get_applicable_dimensions("cp")
        dim_names = {d.name for d in dims}
        assert "activity" in dim_names
        assert "time_of_day" in dim_names
        assert "metabolic" in dim_names
        assert "emotional" in dim_names
        assert "technique" not in dim_names


class TestGetApplicableValues:
    """Test get_applicable_values function."""

    def test_hr_values(self):
        """HR entries can have all condition values except technique."""
        values = get_applicable_values("hr")
        assert "resting" in values
        assert "postprandial" in values
        assert "stressed" in values
        assert "morning" in values
        # Technique not applicable to HR
        assert "oral" not in values

    def test_temp_values(self):
        """Temperature entries can have all condition values including technique."""
        values = get_applicable_values("temp")
        assert "oral" in values
        assert "underarm" in values
        assert "postprandial" in values
        assert "morning" in values
        assert "stressed" in values  # All dimensions apply to temp


class TestParseConditions:
    """Test parse_conditions function."""

    def test_single_condition(self):
        """Parse single condition."""
        result = parse_conditions(["resting"], "hr")
        assert result == "resting"

    def test_multiple_conditions_sorted(self):
        """Multiple conditions sorted by dimension priority."""
        # postprandial (metabolic, priority 3) should come after resting (activity, priority 1)
        result = parse_conditions(["postprandial", "resting"], "hr")
        assert result == "resting,postprandial"

    def test_input_order_independent(self):
        """Same result regardless of input order."""
        result1 = parse_conditions(["resting", "postprandial"], "hr")
        result2 = parse_conditions(["postprandial", "resting"], "hr")
        assert result1 == result2 == "resting,postprandial"

    def test_no_valid_conditions_returns_none(self):
        """No valid conditions returns None."""
        result = parse_conditions(["invalid", "tokens"], "hr")
        assert result is None

    def test_empty_tokens_returns_none(self):
        """Empty token list returns None."""
        result = parse_conditions([], "hr")
        assert result is None

    def test_with_aliases(self):
        """Aliases are resolved."""
        aliases = {"rest": "resting", "pp": "postprandial"}
        result = parse_conditions(["rest", "pp"], "hr", aliases)
        assert result == "resting,postprandial"

    def test_temp_with_technique_and_metabolic(self):
        """Temperature with technique and metabolic condition."""
        result = parse_conditions(["oral", "postprandial"], "temp")
        # metabolic (priority 3) before technique (priority 5)
        assert result == "postprandial,oral"

    def test_conflict_same_dimension_raises(self):
        """Multiple values from same dimension raises error."""
        with pytest.raises(ConditionConflictError) as exc_info:
            parse_conditions(["resting", "active"], "hr")
        assert exc_info.value.dimension == "activity"
        assert "resting" in exc_info.value.values
        assert "active" in exc_info.value.values

    def test_invalid_condition_for_entry_type_raises(self):
        """Condition not applicable to entry type raises error."""
        with pytest.raises(InvalidConditionError) as exc_info:
            parse_conditions(["oral"], "hr")  # technique not valid for HR
        assert exc_info.value.value == "oral"
        assert exc_info.value.entry_type == "hr"


class TestValidateConditionsString:
    """Test validate_conditions_string function."""

    def test_valid_single_condition(self):
        """Valid single condition passes."""
        assert validate_conditions_string("resting", "hr") is True

    def test_valid_multiple_conditions(self):
        """Valid multiple conditions pass."""
        assert validate_conditions_string("resting,postprandial", "hr") is True

    def test_none_is_valid(self):
        """None is valid (no conditions)."""
        assert validate_conditions_string(None, "hr") is True

    def test_invalid_value_raises(self):
        """Invalid value raises error."""
        with pytest.raises(InvalidConditionError):
            validate_conditions_string("invalid_value", "hr")

    def test_wrong_entry_type_raises(self):
        """Value not applicable to entry type raises error."""
        with pytest.raises(InvalidConditionError):
            validate_conditions_string("oral", "hr")


class TestFormatConditions:
    """Test format_conditions function."""

    def test_single_condition(self):
        """Single condition formatted with parens."""
        assert format_conditions("resting") == "(resting)"

    def test_multiple_conditions(self):
        """Multiple conditions separated with comma and space."""
        assert format_conditions("resting,postprandial") == "(resting, postprandial)"

    def test_none_returns_empty(self):
        """None returns empty string."""
        assert format_conditions(None) == ""

    def test_empty_returns_empty(self):
        """Empty string returns empty string."""
        assert format_conditions("") == ""
