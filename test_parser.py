"""Tests for the health tracker parser."""

import pytest
from datetime import datetime
from parser import (
    Parser,
    ParsedExercise,
    ParsedHeartRate,
    ParsedHRV,
    ParsedTemperature,
    ParsedBodyweight,
    ParsedControlPause,
)


@pytest.fixture
def parser():
    """Create a parser with the default aliases."""
    return Parser()


@pytest.fixture
def now():
    """Fixed datetime for consistent testing."""
    return datetime(2026, 1, 10, 14, 30, 0)


# =============================================================================
# Reps Format Tests
# =============================================================================

class TestRepsFormats:
    """Test parsing of different reps formats."""

    def test_nxm_format_3x5(self, parser, now):
        """NxM format: 3x5 -> [5, 5, 5]"""
        result = parser.parse("squat 100 3x5", now)
        assert isinstance(result, ParsedExercise)
        assert result.reps == [5, 5, 5]

    def test_nxm_format_5x10(self, parser, now):
        """NxM format: 5x10 -> [10, 10, 10, 10, 10]"""
        result = parser.parse("pullups 5x10", now)
        assert result.reps == [10, 10, 10, 10, 10]

    def test_nxm_format_1x1(self, parser, now):
        """NxM format: 1x1 -> [1] (single heavy set)"""
        result = parser.parse("deadlift 200 1x1", now)
        assert result.reps == [1]

    def test_comma_separated_equal(self, parser, now):
        """Comma-separated with equal reps: 5,5,5 -> [5, 5, 5]"""
        result = parser.parse("bench 80 5,5,5", now)
        assert result.reps == [5, 5, 5]

    def test_comma_separated_pyramid(self, parser, now):
        """Comma-separated pyramid: 8,6,4,2 -> [8, 6, 4, 2]"""
        result = parser.parse("squat 120 8,6,4,2", now)
        assert result.reps == [8, 6, 4, 2]

    def test_comma_separated_amrap(self, parser, now):
        """Comma-separated with AMRAP last set: 5,5,8 -> [5, 5, 8]"""
        result = parser.parse("ohp 50 5,5,8", now)
        assert result.reps == [5, 5, 8]

    def test_single_number(self, parser, now):
        """Single number: 10 -> [10]"""
        result = parser.parse("pushups 10", now)
        assert result.reps == [10]

    def test_single_number_with_weight(self, parser, now):
        """Single number with weight: 5 -> [5]"""
        result = parser.parse("curl 20 5", now)
        assert result.reps == [5]


# =============================================================================
# Alias Resolution Tests
# =============================================================================

class TestAliasResolution:
    """Test alias resolution for exercises and contexts."""

    # Exercise aliases
    def test_exercise_alias_sq(self, parser, now):
        """sq -> squat"""
        result = parser.parse("sq 100 3x5", now)
        assert result.name == "squat"

    def test_exercise_alias_bp(self, parser, now):
        """bp -> bench press"""
        result = parser.parse("bp 80 5,5,5", now)
        assert result.name == "bench press"

    def test_exercise_alias_dl(self, parser, now):
        """dl -> deadlift"""
        result = parser.parse("dl 150 1x5", now)
        assert result.name == "deadlift"

    def test_exercise_alias_ohp(self, parser, now):
        """ohp -> overhead press"""
        result = parser.parse("ohp 50 3x8", now)
        assert result.name == "overhead press"

    def test_exercise_alias_pu(self, parser, now):
        """pu -> pullups"""
        result = parser.parse("pu 3x10", now)
        assert result.name == "pullups"

    def test_exercise_alias_rdl(self, parser, now):
        """rdl -> romanian deadlift"""
        result = parser.parse("rdl 80 3x10", now)
        assert result.name == "romanian deadlift"

    def test_exercise_no_alias(self, parser, now):
        """Unknown exercise names pass through unchanged."""
        result = parser.parse("kettlebell_swing 24 3x15", now)
        assert result.name == "kettlebell_swing"

    # Heart rate context aliases
    def test_hr_context_alias_rest(self, parser, now):
        """rest -> resting"""
        result = parser.parse("hr 60 rest", now)
        assert result.context == "resting"

    def test_hr_context_alias_workout(self, parser, now):
        """workout -> post-workout"""
        result = parser.parse("hr 120 workout", now)
        assert result.context == "post-workout"

    def test_hr_context_alias_post(self, parser, now):
        """post -> post-workout"""
        result = parser.parse("hr 110 post", now)
        assert result.context == "post-workout"

    def test_hr_context_alias_stress(self, parser, now):
        """stress -> stressed"""
        result = parser.parse("hr 90 stress", now)
        assert result.context == "stressed"

    def test_hr_invalid_context_ignored(self, parser, now):
        """Invalid context is ignored."""
        result = parser.parse("hr 70 walking", now)
        assert result.context is None

    # Temperature technique aliases
    def test_temp_technique_alias_arm(self, parser, now):
        """arm -> underarm"""
        result = parser.parse("temp 36.5 arm", now)
        assert result.technique == "underarm"

    def test_temp_technique_alias_ir(self, parser, now):
        """ir -> forehead_ir"""
        result = parser.parse("temp 36.8 ir", now)
        assert result.technique == "forehead_ir"

    def test_temp_technique_alias_mouth(self, parser, now):
        """mouth -> oral"""
        result = parser.parse("temp 37.0 mouth", now)
        assert result.technique == "oral"

    def test_temp_technique_alias_tympanic(self, parser, now):
        """tympanic -> ear"""
        result = parser.parse("temp 37.2 tympanic", now)
        assert result.technique == "ear"

    # Postprandial context aliases
    def test_hr_context_alias_pp(self, parser, now):
        """pp -> postprandial"""
        result = parser.parse("hr 85 pp", now)
        assert result.context == "postprandial"

    def test_hr_context_alias_fed(self, parser, now):
        """fed -> postprandial"""
        result = parser.parse("hr 88 fed", now)
        assert result.context == "postprandial"

    def test_hr_context_alias_meal(self, parser, now):
        """meal -> postprandial"""
        result = parser.parse("hr 82 meal", now)
        assert result.context == "postprandial"

    # Temperature context aliases
    def test_temp_context_alias_pp(self, parser, now):
        """pp -> postprandial for temperature"""
        result = parser.parse("temp 37.1 pp", now)
        assert result.context == "postprandial"

    def test_temp_with_technique_and_context(self, parser, now):
        """Temperature with both technique and context."""
        result = parser.parse("temp 37.2 oral pp", now)
        assert result.technique == "oral"
        assert result.context == "postprandial"

    def test_temp_with_context_and_technique(self, parser, now):
        """Temperature with context before technique (order shouldn't matter)."""
        result = parser.parse("temp 37.2 pp oral", now)
        assert result.technique == "oral"
        assert result.context == "postprandial"


# =============================================================================
# Timestamp Parsing Tests
# =============================================================================

class TestTimestampParsing:
    """Test @timestamp parsing."""

    def test_time_hhmm(self, parser, now):
        """@HH:MM sets specific time."""
        result = parser.parse("hr 65 rest @08:30", now)
        assert result.timestamp.hour == 8
        assert result.timestamp.minute == 30
        assert result.timestamp.year == now.year
        assert result.timestamp.month == now.month
        assert result.timestamp.day == now.day

    def test_time_single_digit_hour(self, parser, now):
        """@H:MM works for single digit hours."""
        result = parser.parse("temp 36.5 @7:00", now)
        assert result.timestamp.hour == 7
        assert result.timestamp.minute == 0

    def test_yesterday(self, parser, now):
        """@yesterday sets to yesterday at midnight."""
        result = parser.parse("weight 80 @yesterday", now)
        assert result.timestamp.day == now.day - 1
        assert result.timestamp.hour == 0
        assert result.timestamp.minute == 0
        assert result.timestamp.second == 0

    def test_date_format(self, parser, now):
        """@YYYY-MM-DD sets specific date."""
        result = parser.parse("squat 100 3x5 @2026-01-05", now)
        assert result.timestamp.year == 2026
        assert result.timestamp.month == 1
        assert result.timestamp.day == 5

    def test_timestamp_at_start(self, parser, now):
        """Timestamp can appear at start of input."""
        result = parser.parse("@14:00 hr 70 rest", now)
        assert result.timestamp.hour == 14
        assert isinstance(result, ParsedHeartRate)
        assert result.bpm == 70

    def test_timestamp_in_middle(self, parser, now):
        """Timestamp can appear in middle of input."""
        result = parser.parse("squat @09:00 100 3x5", now)
        assert result.timestamp.hour == 9
        assert result.name == "squat"

    def test_no_timestamp_uses_now(self, parser, now):
        """No timestamp uses the provided 'now' time."""
        result = parser.parse("hr 60 rest", now)
        assert result.timestamp == now


# =============================================================================
# Exercise Parsing Tests
# =============================================================================

class TestExerciseParsing:
    """Test exercise entry parsing."""

    def test_exercise_with_weight_and_reps(self, parser, now):
        """Basic exercise with weight and reps."""
        result = parser.parse("squat 100 3x5", now)
        assert result.name == "squat"
        assert result.weight_kg == 100.0
        assert result.reps == [5, 5, 5]
        assert result.rpe is None

    def test_exercise_with_rpe(self, parser, now):
        """Exercise with RPE."""
        result = parser.parse("deadlift 150 1x5 8", now)
        assert result.name == "deadlift"
        assert result.weight_kg == 150.0
        assert result.reps == [5]
        assert result.rpe == 8.0

    def test_exercise_with_rpe_prefix(self, parser, now):
        """Exercise with rpe prefix."""
        result = parser.parse("squat 120 5,5,5 rpe9", now)
        assert result.rpe == 9.0

    def test_exercise_decimal_rpe(self, parser, now):
        """Exercise with decimal RPE."""
        result = parser.parse("bench 80 3x5 7.5", now)
        assert result.rpe == 7.5

    def test_exercise_bodyweight_no_weight(self, parser, now):
        """Bodyweight exercise without weight specified."""
        result = parser.parse("pullups 3x10", now)
        assert result.name == "pullups"
        assert result.weight_kg is None
        assert result.reps == [10, 10, 10]

    def test_exercise_decimal_weight(self, parser, now):
        """Exercise with decimal weight."""
        result = parser.parse("ohp 42.5 3x5", now)
        assert result.weight_kg == 42.5

    def test_exercise_weight_with_kg_suffix(self, parser, now):
        """Exercise with kg suffix on weight."""
        result = parser.parse("squat 100kg 3x5", now)
        assert result.weight_kg == 100.0

    def test_exercise_case_insensitive(self, parser, now):
        """Exercise names are case insensitive."""
        result = parser.parse("SQUAT 100 3x5", now)
        assert result.name == "squat"

    def test_exercise_rpe_out_of_range_ignored(self, parser, now):
        """RPE > 10 is not parsed as RPE."""
        result = parser.parse("squat 100 3x5 15", now)
        assert result.rpe is None

    def test_exercise_rpe_zero_ignored(self, parser, now):
        """RPE 0 is not valid (must be 1-10)."""
        result = parser.parse("squat 100 3x5 0", now)
        assert result.rpe is None


# =============================================================================
# Health Metric Parsing Tests
# =============================================================================

class TestHeartRateParsing:
    """Test heart rate entry parsing."""

    def test_hr_basic(self, parser, now):
        """Basic heart rate."""
        result = parser.parse("hr 72", now)
        assert isinstance(result, ParsedHeartRate)
        assert result.bpm == 72
        assert result.context is None

    def test_hr_with_context(self, parser, now):
        """Heart rate with context."""
        result = parser.parse("hr 58 resting", now)
        assert result.bpm == 58
        assert result.context == "resting"

    def test_hr_high_bpm(self, parser, now):
        """High heart rate (post-workout)."""
        result = parser.parse("hr 165 post-workout", now)
        assert result.bpm == 165
        assert result.context == "post-workout"


class TestHRVParsing:
    """Test HRV entry parsing."""

    def test_hrv_basic(self, parser, now):
        """Basic HRV defaults to rmssd."""
        result = parser.parse("hrv 45", now)
        assert isinstance(result, ParsedHRV)
        assert result.ms == 45.0
        assert result.metric == "rmssd"
        assert result.context is None

    def test_hrv_with_metric(self, parser, now):
        """HRV with explicit metric."""
        result = parser.parse("hrv 50 sdnn", now)
        assert result.metric == "sdnn"

    def test_hrv_with_context(self, parser, now):
        """HRV with context."""
        result = parser.parse("hrv 55 rmssd morning", now)
        assert result.ms == 55.0
        assert result.metric == "rmssd"
        assert result.context == "morning"

    def test_hrv_decimal(self, parser, now):
        """HRV with decimal value."""
        result = parser.parse("hrv 42.5 rmssd", now)
        assert result.ms == 42.5


class TestTemperatureParsing:
    """Test temperature entry parsing."""

    def test_temp_basic(self, parser, now):
        """Basic temperature."""
        result = parser.parse("temp 36.6", now)
        assert isinstance(result, ParsedTemperature)
        assert result.celsius == 36.6
        assert result.technique is None

    def test_temp_with_technique(self, parser, now):
        """Temperature with technique."""
        result = parser.parse("temp 36.8 oral", now)
        assert result.celsius == 36.8
        assert result.technique == "oral"

    def test_temp_integer(self, parser, now):
        """Temperature as integer."""
        result = parser.parse("temp 37", now)
        assert result.celsius == 37.0


class TestBodyweightParsing:
    """Test bodyweight entry parsing."""

    def test_weight_basic(self, parser, now):
        """Basic bodyweight with 'weight' prefix."""
        result = parser.parse("weight 82.5", now)
        assert isinstance(result, ParsedBodyweight)
        assert result.kg == 82.5
        assert result.bodyfat_pct is None

    def test_bw_prefix(self, parser, now):
        """Bodyweight with 'bw' prefix."""
        result = parser.parse("bw 80", now)
        assert isinstance(result, ParsedBodyweight)
        assert result.kg == 80.0

    def test_weight_with_bodyfat(self, parser, now):
        """Bodyweight with body fat percentage."""
        result = parser.parse("weight 85 18", now)
        assert result.kg == 85.0
        assert result.bodyfat_pct == 18.0

    def test_weight_with_bodyfat_percent(self, parser, now):
        """Bodyweight with body fat using % suffix."""
        result = parser.parse("bw 82 15%", now)
        assert result.kg == 82.0
        assert result.bodyfat_pct == 15.0

    def test_weight_decimal_bodyfat(self, parser, now):
        """Bodyweight with decimal body fat."""
        result = parser.parse("weight 80 17.5", now)
        assert result.bodyfat_pct == 17.5


class TestControlPauseParsing:
    """Test control pause entry parsing."""

    def test_cp_basic(self, parser, now):
        """Basic control pause with cp prefix."""
        result = parser.parse("cp 45", now)
        assert isinstance(result, ParsedControlPause)
        assert result.seconds == 45
        assert result.context is None

    def test_pause_prefix(self, parser, now):
        """Control pause with pause prefix."""
        result = parser.parse("pause 30", now)
        assert isinstance(result, ParsedControlPause)
        assert result.seconds == 30

    def test_cp_with_s_suffix(self, parser, now):
        """Control pause with 's' suffix on seconds."""
        result = parser.parse("cp 60s", now)
        assert result.seconds == 60

    def test_cp_with_morning_context(self, parser, now):
        """Control pause with morning context."""
        result = parser.parse("cp 45 morning", now)
        assert result.seconds == 45
        assert result.context == "morning"

    def test_cp_with_evening_context(self, parser, now):
        """Control pause with evening context."""
        result = parser.parse("cp 50 evening", now)
        assert result.seconds == 50
        assert result.context == "evening"

    def test_cp_invalid_context_ignored(self, parser, now):
        """Invalid context is ignored."""
        result = parser.parse("cp 40 afternoon", now)
        assert result.seconds == 40
        assert result.context is None

    def test_cp_with_timestamp(self, parser, now):
        """Control pause with timestamp."""
        result = parser.parse("cp 35 morning @08:00", now)
        assert result.seconds == 35
        assert result.context == "morning"
        assert result.timestamp.hour == 8


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_input_raises(self, parser, now):
        """Empty input raises ValueError."""
        with pytest.raises(ValueError, match="Empty input"):
            parser.parse("", now)

    def test_whitespace_only_raises(self, parser, now):
        """Whitespace-only input raises ValueError."""
        with pytest.raises(ValueError, match="Empty input"):
            parser.parse("   ", now)

    def test_exercise_no_reps_raises(self, parser, now):
        """Exercise without reps raises ValueError."""
        with pytest.raises(ValueError, match="Exercise needs at least name and reps"):
            parser.parse("squat", now)

    def test_exercise_single_number_is_reps(self, parser, now):
        """Single number after exercise name is treated as reps, not weight."""
        result = parser.parse("squat 100", now)
        # 100 is parsed as reps (100 reps!), not as weight
        assert result.reps == [100]
        assert result.weight_kg is None

    def test_hr_no_bpm_raises(self, parser, now):
        """Heart rate without BPM raises ValueError."""
        with pytest.raises(ValueError, match="Heart rate needs BPM value"):
            parser.parse("hr", now)

    def test_hrv_no_value_raises(self, parser, now):
        """HRV without ms value raises ValueError."""
        with pytest.raises(ValueError, match="HRV needs milliseconds value"):
            parser.parse("hrv", now)

    def test_temp_no_value_raises(self, parser, now):
        """Temperature without value raises ValueError."""
        with pytest.raises(ValueError, match="Temperature needs Celsius value"):
            parser.parse("temp", now)

    def test_weight_no_value_raises(self, parser, now):
        """Bodyweight without value raises ValueError."""
        with pytest.raises(ValueError, match="Bodyweight needs kg value"):
            parser.parse("weight", now)

    def test_cp_no_value_raises(self, parser, now):
        """Control pause without value raises ValueError."""
        with pytest.raises(ValueError, match="Control pause needs seconds value"):
            parser.parse("cp", now)

    def test_case_insensitive_prefixes(self, parser, now):
        """All prefixes are case insensitive."""
        assert isinstance(parser.parse("HR 70", now), ParsedHeartRate)
        assert isinstance(parser.parse("HRV 50", now), ParsedHRV)
        assert isinstance(parser.parse("TEMP 36.5", now), ParsedTemperature)
        assert isinstance(parser.parse("WEIGHT 80", now), ParsedBodyweight)
        assert isinstance(parser.parse("BW 80", now), ParsedBodyweight)
        assert isinstance(parser.parse("CP 45", now), ParsedControlPause)
        assert isinstance(parser.parse("PAUSE 45", now), ParsedControlPause)

    def test_extra_whitespace_handled(self, parser, now):
        """Extra whitespace is handled gracefully."""
        result = parser.parse("  squat   100   3x5  ", now)
        assert result.name == "squat"
        assert result.weight_kg == 100.0


# =============================================================================
# Format Response Tests
# =============================================================================

class TestFormatResponse:
    """Test the format_response method for each entry type."""

    def test_exercise_format_with_weight(self, parser, now):
        result = parser.parse("squat 100 3x5 8", now)
        assert result.format_response() == "squat 100.0kg [5,5,5] RPE 8.0"

    def test_exercise_format_bodyweight(self, parser, now):
        result = parser.parse("pullups 3x10", now)
        assert result.format_response() == "pullups (BW) [10,10,10]"

    def test_hr_format_with_context(self, parser, now):
        result = parser.parse("hr 60 resting", now)
        assert result.format_response() == "HR 60 bpm (resting)"

    def test_hr_format_no_context(self, parser, now):
        result = parser.parse("hr 72", now)
        assert result.format_response() == "HR 72 bpm"

    def test_hrv_format(self, parser, now):
        result = parser.parse("hrv 45 rmssd morning", now)
        assert result.format_response() == "HRV 45.0ms (rmssd) (morning)"

    def test_temp_format(self, parser, now):
        result = parser.parse("temp 36.6 oral", now)
        assert result.format_response() == "Temp 36.6°C (oral)"

    def test_temp_format_with_context(self, parser, now):
        result = parser.parse("temp 37.1 oral pp", now)
        assert result.format_response() == "Temp 37.1°C (oral) [postprandial]"

    def test_weight_format_with_bf(self, parser, now):
        result = parser.parse("weight 80 15", now)
        assert result.format_response() == "Weight 80.0kg (15.0% BF)"

    def test_cp_format_with_context(self, parser, now):
        result = parser.parse("cp 45 morning", now)
        assert result.format_response() == "CP 45s (morning)"

    def test_cp_format_no_context(self, parser, now):
        result = parser.parse("cp 35", now)
        assert result.format_response() == "CP 35s"


# =============================================================================
# to_dict Tests
# =============================================================================

class TestToDict:
    """Test the to_dict method for JSON serialization."""

    def test_exercise_to_dict(self, parser, now):
        result = parser.parse("squat 100 3x5 8", now)
        d = result.to_dict()
        assert d["type"] == "exercise"
        assert d["name"] == "squat"
        assert d["weight_kg"] == 100.0
        assert d["reps"] == [5, 5, 5]
        assert d["rpe"] == 8.0
        assert "timestamp" in d

    def test_hr_to_dict(self, parser, now):
        result = parser.parse("hr 60 resting", now)
        d = result.to_dict()
        assert d["type"] == "hr"
        assert d["bpm"] == 60
        assert d["context"] == "resting"

    def test_hrv_to_dict(self, parser, now):
        result = parser.parse("hrv 45", now)
        d = result.to_dict()
        assert d["type"] == "hrv"
        assert d["ms"] == 45.0
        assert d["metric"] == "rmssd"

    def test_temp_to_dict(self, parser, now):
        result = parser.parse("temp 36.6", now)
        d = result.to_dict()
        assert d["type"] == "temp"
        assert d["celsius"] == 36.6

    def test_temp_to_dict_with_context(self, parser, now):
        result = parser.parse("temp 37.1 oral pp", now)
        d = result.to_dict()
        assert d["type"] == "temp"
        assert d["celsius"] == 37.1
        assert d["technique"] == "oral"
        assert d["context"] == "postprandial"

    def test_weight_to_dict(self, parser, now):
        result = parser.parse("weight 80", now)
        d = result.to_dict()
        assert d["type"] == "weight"
        assert d["kg"] == 80.0

    def test_cp_to_dict(self, parser, now):
        result = parser.parse("cp 45 morning", now)
        d = result.to_dict()
        assert d["type"] == "cp"
        assert d["seconds"] == 45
        assert d["context"] == "morning"
        assert "timestamp" in d
