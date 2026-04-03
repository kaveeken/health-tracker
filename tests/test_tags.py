"""Tests for the tags functionality."""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from parser import Parser, ParsedHeartRate, ParsedBodyweight, ParsedExercise
from db import Database


@pytest.fixture
def parser():
    """Create a parser with default aliases."""
    return Parser()


@pytest.fixture
def db():
    """Create a test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    database = Database(db_path)
    yield database
    db_path.unlink(missing_ok=True)


class TestTagExtraction:
    """Tests for extracting @tags from input."""

    def test_single_tag(self, parser):
        """Single @tag is extracted."""
        result = parser.parse("hr 60 @oura")
        assert result.tags == ["oura"]
        assert result.bpm == 60

    def test_multiple_tags(self, parser):
        """Multiple @tags are extracted."""
        result = parser.parse("hr 60 @oura @morning-check")
        assert result.tags == ["oura", "morning-check"]

    def test_tag_with_conditions(self, parser):
        """Tags work alongside conditions."""
        result = parser.parse("hr 60 resting @oura")
        assert result.tags == ["oura"]
        assert result.conditions == "resting"

    def test_tag_position_flexible(self, parser):
        """Tags can appear anywhere in input."""
        result = parser.parse("@oura hr 60 resting")
        assert result.tags == ["oura"]
        assert result.bpm == 60

    def test_tag_case_normalized(self, parser):
        """Tags are lowercase normalized."""
        result = parser.parse("hr 60 @OURA @MyTag")
        assert result.tags == ["oura", "mytag"]

    def test_no_tag(self, parser):
        """No tag returns None."""
        result = parser.parse("hr 60 resting")
        assert result.tags is None

    def test_tag_not_confused_with_timestamp(self, parser):
        """@HH:MM is timestamp, not tag."""
        result = parser.parse("hr 60 @14:30")
        assert result.tags is None
        assert result.timestamp.hour == 14
        assert result.timestamp.minute == 30

    def test_tag_not_confused_with_yesterday(self, parser):
        """@yesterday is timestamp, not tag."""
        result = parser.parse("hr 60 @yesterday")
        assert result.tags is None

    def test_duplicate_tags_deduplicated(self, parser):
        """Duplicate tags are removed."""
        result = parser.parse("hr 60 @oura @oura")
        assert result.tags == ["oura"]

    def test_tag_with_numbers(self, parser):
        """Tags can contain numbers (not at start)."""
        result = parser.parse("hr 60 @sensor2")
        assert result.tags == ["sensor2"]

    def test_tag_with_hyphen(self, parser):
        """Tags can contain hyphens."""
        result = parser.parse("hr 60 @my-tag")
        assert result.tags == ["my-tag"]

    def test_tag_with_underscore(self, parser):
        """Tags can contain underscores."""
        result = parser.parse("hr 60 @my_tag")
        assert result.tags == ["my_tag"]


class TestTagAliases:
    """Tests for tag alias resolution."""

    def test_tag_alias_resolved(self):
        """Tag aliases are resolved."""
        # Create parser with tag alias
        import json
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "exercises": {},
                "conditions": {},
                "tags": {"fitbit": "oura", "ps": "personal_scale"}
            }, f)
            aliases_path = Path(f.name)

        try:
            parser = Parser(aliases_path)
            result = parser.parse("hr 60 @fitbit")
            assert result.tags == ["oura"]

            result2 = parser.parse("weight 85 @ps")
            assert result2.tags == ["personal_scale"]
        finally:
            aliases_path.unlink(missing_ok=True)


class TestTagInAllEntryTypes:
    """Test that tags work with all entry types."""

    def test_exercise_with_tag(self, parser):
        """Exercise entries support tags."""
        result = parser.parse("squat 100 3x5 @gym")
        assert isinstance(result, ParsedExercise)
        assert result.tags == ["gym"]

    def test_hr_with_tag(self, parser):
        """Heart rate entries support tags."""
        result = parser.parse("hr 60 @oura")
        assert isinstance(result, ParsedHeartRate)
        assert result.tags == ["oura"]

    def test_weight_with_tag(self, parser):
        """Weight entries support tags."""
        result = parser.parse("weight 85 @ps")
        assert isinstance(result, ParsedBodyweight)
        assert result.tags == ["ps"]

    def test_hrv_with_tag(self, parser):
        """HRV entries support tags."""
        result = parser.parse("hrv 45 @oura")
        assert result.tags == ["oura"]

    def test_temp_with_tag(self, parser):
        """Temperature entries support tags."""
        result = parser.parse("temp 36.8 @thermometer")
        assert result.tags == ["thermometer"]

    def test_cp_with_tag(self, parser):
        """Control pause entries support tags."""
        result = parser.parse("cp 45 @morning")
        # Note: @morning could be a tag, depends on whether it matches timestamp
        # In this case it doesn't match any timestamp pattern
        assert result.tags == ["morning"]


class TestFormatResponseWithTags:
    """Test format_response includes tags."""

    def test_hr_format_with_tag(self, parser):
        """Heart rate format includes tag."""
        result = parser.parse("hr 60 resting @oura")
        formatted = result.format_response()
        assert "@oura" in formatted

    def test_exercise_format_with_tag(self, parser):
        """Exercise format includes tag."""
        result = parser.parse("squat 100 3x5 @gym")
        formatted = result.format_response()
        assert "@gym" in formatted

    def test_multiple_tags_formatted(self, parser):
        """Multiple tags are formatted."""
        result = parser.parse("hr 60 @oura @check")
        formatted = result.format_response()
        assert "@oura" in formatted
        assert "@check" in formatted


class TestToDictWithTags:
    """Test to_dict includes tags."""

    def test_hr_to_dict_with_tag(self, parser):
        """Heart rate to_dict includes tags."""
        result = parser.parse("hr 60 @oura")
        d = result.to_dict()
        assert d["tags"] == ["oura"]

    def test_to_dict_no_tag(self, parser):
        """to_dict with no tags has None."""
        result = parser.parse("hr 60")
        d = result.to_dict()
        assert d["tags"] is None


class TestDatabaseTagStorage:
    """Tests for tag storage in database."""

    def test_create_entry_with_tag(self, parser, db):
        """Creating entry stores tag."""
        parsed = parser.parse("hr 60 @oura")
        hash_code = db.create_entry("hr 60 @oura", parsed)

        tags = db.get_all_tags()
        assert len(tags) == 1
        assert tags[0]["tag"] == "oura"
        assert tags[0]["use_count"] == 1

    def test_tag_count_incremented(self, parser, db):
        """Tag use_count incremented on reuse."""
        parsed1 = parser.parse("hr 60 @oura")
        db.create_entry("hr 60 @oura", parsed1)

        parsed2 = parser.parse("hr 65 @oura")
        db.create_entry("hr 65 @oura", parsed2)

        tags = db.get_all_tags()
        assert len(tags) == 1
        assert tags[0]["use_count"] == 2

    def test_get_tag_count_by_type(self, parser, db):
        """get_tag_count returns count for specific entry type."""
        parsed1 = parser.parse("hr 60 @oura")
        db.create_entry("hr 60 @oura", parsed1)

        parsed2 = parser.parse("hrv 45 @oura")
        db.create_entry("hrv 45 @oura", parsed2)

        hr_count = db.get_tag_count("oura", "hr")
        assert hr_count == 1

        hrv_count = db.get_tag_count("oura", "hrv")
        assert hrv_count == 1

    def test_multiple_tags_stored(self, parser, db):
        """Multiple tags on one entry are stored."""
        parsed = parser.parse("hr 60 @oura @morning")
        db.create_entry("hr 60 @oura @morning", parsed)

        tags = db.get_all_tags()
        tag_names = [t["tag"] for t in tags]
        assert "oura" in tag_names
        assert "morning" in tag_names

    def test_update_entry_replaces_tags(self, parser, db):
        """Updating entry replaces tags."""
        parsed1 = parser.parse("hr 60 @oura")
        hash_code = db.create_entry("hr 60 @oura", parsed1)

        # Update with different tag
        parsed2 = parser.parse("hr 65 @fitbit")
        db.update_entry(hash_code, "hr 65 @fitbit", parsed2)

        # Should have both tags in user_tags (counts not decremented)
        tags = db.get_all_tags()
        tag_names = [t["tag"] for t in tags]
        assert "oura" in tag_names
        assert "fitbit" in tag_names

        # But only fitbit should be counted for hr entries
        fitbit_count = db.get_tag_count("fitbit", "hr")
        assert fitbit_count == 1

        oura_count = db.get_tag_count("oura", "hr")
        assert oura_count == 0  # Entry was updated, tag removed

    def test_entry_without_tags(self, parser, db):
        """Entry without tags doesn't create tag records."""
        parsed = parser.parse("hr 60")
        db.create_entry("hr 60", parsed)

        tags = db.get_all_tags()
        assert len(tags) == 0
