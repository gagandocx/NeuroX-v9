"""Tests for choppy_filter.py - Multi-indicator ranging/choppy market detection."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from choppy_filter import is_market_choppy
from config import Config


class TestChoppyFilterBasic:
    """Basic tests for the choppy filter."""

    def test_filter_disabled_returns_false(self, monkeypatch):
        """When CHOPPY_FILTER_ENABLED is False, always returns not choppy."""
        monkeypatch.setattr(Config, "CHOPPY_FILTER_ENABLED", False)
        result, reason = is_market_choppy(adx_value=10.0, choppiness_index=80.0)
        assert result is False
        assert reason == ""

    def test_all_clear_trending_market(self):
        """Strong trending market should not be flagged as choppy."""
        result, reason = is_market_choppy(
            adx_value=35.0,           # Above 20 threshold - trending
            choppiness_index=40.0,    # Below 61.8 - not choppy
            bb_upper=2010.0,
            bb_lower=1990.0,
            current_price=2000.0,     # BB width = 20/2000 * 100 = 1.0% > 0.5%
            current_atr=1.5,
            avg_atr=1.2,              # Ratio = 1.25 > 0.75
            variance_ratio=1.2,       # Above 0.5
        )
        assert result is False
        assert reason == ""

    def test_all_indicators_ranging(self):
        """All indicators showing ranging should definitely be choppy."""
        result, reason = is_market_choppy(
            adx_value=12.0,           # Below 20 - ranging
            choppiness_index=75.0,    # Above 61.8 - choppy
            bb_upper=2001.0,
            bb_lower=1999.0,
            current_price=2000.0,     # BB width = 2/2000 * 100 = 0.1% < 0.5% squeeze
            current_atr=0.5,
            avg_atr=1.0,              # Ratio = 0.5 < 0.75
            variance_ratio=0.3,       # Below 0.5 - mean reverting
        )
        assert result is True
        assert "ADX" in reason
        assert "CI" in reason

    def test_default_values_not_choppy(self):
        """Default values (no data from EA) should not trigger choppy."""
        result, reason = is_market_choppy(
            adx_value=100.0,         # Default high value
            choppiness_index=0.0,    # Default zero
            bb_upper=0.0,
            bb_lower=0.0,
            current_price=2000.0,
        )
        assert result is False


class TestChoppyFilterADX:
    """Test ADX indicator within choppy filter."""

    def test_adx_below_threshold_counts(self):
        """ADX below MIN_ADX_THRESHOLD should contribute one vote."""
        result, reason = is_market_choppy(
            adx_value=15.0,           # Below 20
            choppiness_index=70.0,    # Above 61.8 - second vote
        )
        assert result is True
        assert "ADX=15.0<20.0" in reason

    def test_adx_at_threshold_does_not_count(self):
        """ADX exactly at threshold should not count as ranging."""
        result, reason = is_market_choppy(
            adx_value=20.0,           # Not below threshold
            choppiness_index=0.0,
        )
        assert result is False

    def test_adx_above_threshold_does_not_count(self):
        """ADX above threshold should not count."""
        result, reason = is_market_choppy(adx_value=30.0)
        assert result is False
        assert "ADX" not in reason


class TestChoppyFilterChoppinessIndex:
    """Test Choppiness Index within choppy filter."""

    def test_ci_above_threshold_counts(self):
        """CI above CHOPPINESS_INDEX_THRESHOLD should contribute one vote."""
        result, reason = is_market_choppy(
            adx_value=15.0,           # First vote
            choppiness_index=65.0,    # Above 61.8 - second vote
        )
        assert result is True
        assert "CI=65.0>61.8" in reason

    def test_ci_below_threshold_does_not_count(self):
        """CI below threshold should not count."""
        result, reason = is_market_choppy(
            adx_value=30.0,
            choppiness_index=50.0,    # Below 61.8
        )
        assert result is False
        assert "CI" not in reason

    def test_ci_zero_does_not_count(self):
        """CI of zero (no data) should not count."""
        result, reason = is_market_choppy(
            adx_value=15.0,
            choppiness_index=0.0,     # Zero = no data
        )
        # Only ADX vote, need 2 to agree
        assert result is False


class TestChoppyFilterBollingerSqueeze:
    """Test Bollinger Band squeeze detection."""

    def test_bb_squeeze_counts(self):
        """Narrow BB width should contribute one vote."""
        # BB width = 2/2000 * 100 = 0.1% < 0.5%
        result, reason = is_market_choppy(
            adx_value=15.0,           # First vote
            bb_upper=2001.0,
            bb_lower=1999.0,
            current_price=2000.0,     # Squeeze - second vote
        )
        assert result is True
        assert "BB_SQZ" in reason

    def test_bb_wide_does_not_count(self):
        """Wide BB should not count as squeeze."""
        # BB width = 30/2000 * 100 = 1.5% > 0.5%
        result, reason = is_market_choppy(
            adx_value=30.0,
            bb_upper=2015.0,
            bb_lower=1985.0,
            current_price=2000.0,
        )
        assert "BB_SQZ" not in reason

    def test_bb_zero_values_ignored(self):
        """Zero BB values should be ignored."""
        result, reason = is_market_choppy(
            adx_value=15.0,
            bb_upper=0.0,
            bb_lower=0.0,
            current_price=2000.0,
        )
        assert "BB_SQZ" not in reason


class TestChoppyFilterATRRatio:
    """Test ATR ratio indicator."""

    def test_low_atr_ratio_counts(self):
        """Low ATR ratio should contribute one vote."""
        result, reason = is_market_choppy(
            adx_value=15.0,           # First vote
            current_atr=0.5,
            avg_atr=1.0,              # Ratio = 0.5 < 0.75 - second vote
        )
        assert result is True
        assert "ATR_R" in reason

    def test_high_atr_ratio_does_not_count(self):
        """High ATR ratio should not count."""
        result, reason = is_market_choppy(
            adx_value=30.0,
            current_atr=1.5,
            avg_atr=1.0,              # Ratio = 1.5 > 0.75
        )
        assert "ATR_R" not in reason

    def test_zero_atr_ignored(self):
        """Zero ATR values should be ignored (no data)."""
        result, reason = is_market_choppy(
            adx_value=15.0,
            current_atr=0.0,
            avg_atr=0.0,
        )
        assert "ATR_R" not in reason


class TestChoppyFilterVarianceRatio:
    """Test Variance Ratio indicator."""

    def test_low_vr_counts(self):
        """Low variance ratio should contribute one vote."""
        result, reason = is_market_choppy(
            adx_value=15.0,           # First vote
            variance_ratio=0.3,       # Below 0.5 - second vote
        )
        assert result is True
        assert "VR" in reason

    def test_high_vr_does_not_count(self):
        """High variance ratio should not count."""
        result, reason = is_market_choppy(
            adx_value=30.0,
            variance_ratio=1.2,       # Above 0.5
        )
        assert "VR" not in reason

    def test_zero_vr_does_not_count(self):
        """Zero variance ratio should not count (edge case)."""
        result, reason = is_market_choppy(
            adx_value=30.0,
            variance_ratio=0.0,       # Zero - no data
        )
        # VR > 0 check prevents zero from counting
        assert "VR" not in reason


class TestChoppyFilterAgreement:
    """Test the voting/agreement mechanism."""

    def test_single_indicator_not_enough(self):
        """One indicator alone should not trigger (need RANGING_FILTER_AGREEMENT=2)."""
        # Only ADX is ranging
        result, reason = is_market_choppy(
            adx_value=15.0,
            choppiness_index=40.0,    # Not ranging
        )
        assert result is False
        assert "ADX" in reason  # Still reported, just not enough votes

    def test_two_indicators_triggers(self):
        """Two indicators agreeing should trigger choppy (RANGING_FILTER_AGREEMENT=2)."""
        result, reason = is_market_choppy(
            adx_value=15.0,           # Vote 1
            choppiness_index=70.0,    # Vote 2
        )
        assert result is True

    def test_three_indicators_still_triggers(self):
        """Three or more indicators should also trigger."""
        result, reason = is_market_choppy(
            adx_value=15.0,           # Vote 1
            choppiness_index=70.0,    # Vote 2
            variance_ratio=0.3,       # Vote 3
        )
        assert result is True
        assert "ADX" in reason
        assert "CI" in reason
        assert "VR" in reason

    def test_custom_agreement_threshold(self, monkeypatch):
        """Should respect custom RANGING_FILTER_AGREEMENT setting."""
        monkeypatch.setattr(Config, "RANGING_FILTER_AGREEMENT", 3)
        # Only 2 votes - should NOT be choppy now
        result, reason = is_market_choppy(
            adx_value=15.0,           # Vote 1
            choppiness_index=70.0,    # Vote 2
        )
        assert result is False

    def test_agreement_of_1_means_any_indicator(self, monkeypatch):
        """RANGING_FILTER_AGREEMENT=1 means any single indicator triggers."""
        monkeypatch.setattr(Config, "RANGING_FILTER_AGREEMENT", 1)
        result, reason = is_market_choppy(adx_value=15.0)
        assert result is True


class TestChoppyFilterConfig:
    """Test config values for the choppy filter."""

    def test_config_defaults(self):
        """Verify all config defaults are correct."""
        assert Config.CHOPPY_FILTER_ENABLED is True
        assert Config.CHOPPINESS_INDEX_PERIOD == 14
        assert Config.CHOPPINESS_INDEX_THRESHOLD == 61.8
        assert Config.BOLLINGER_BAND_WIDTH_PERIOD == 20
        assert Config.BOLLINGER_SQUEEZE_THRESHOLD == 0.5
        assert Config.ATR_RATIO_PERIOD == 14
        assert Config.ATR_RATIO_RANGING_THRESHOLD == 0.75
        assert Config.VARIANCE_RATIO_THRESHOLD == 0.5
        assert Config.RANGING_FILTER_AGREEMENT == 2
        assert Config.MIN_ADX_THRESHOLD == 20.0

    def test_ema_max_distance_is_080(self):
        """EMA_MAX_DISTANCE should now be 0.80."""
        assert Config.EMA_MAX_DISTANCE == 0.80
