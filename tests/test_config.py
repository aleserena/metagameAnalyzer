"""Unit tests for src.mtgtop8.config (meta value resolution)."""

from src.mtgtop8.config import META_EDH, META_ST, get_meta_value


class TestGetMetaValue:
    """Tests for get_meta_value."""

    def test_edh_period(self):
        """EDH periods resolve from the EDH meta map."""
        assert get_meta_value("EDH", "Last 2 Weeks") == META_EDH["Last 2 Weeks"]

    def test_cedh_uses_edh_map(self):
        """cEDH shares the EDH meta map."""
        assert get_meta_value("cEDH", "Last 2 Months") == META_EDH["Last 2 Months"]

    def test_standard_period(self):
        """Standard periods resolve from the Standard meta map."""
        assert get_meta_value("ST", "Last 2 Weeks") == META_ST["Last 2 Weeks"]

    def test_unmapped_format_returns_none(self):
        """Formats without their own meta map return None instead of guessing EDH IDs."""
        assert get_meta_value("MO", "Last 2 Months") is None

    def test_unmapped_format_returns_none_even_for_edh_period_labels(self):
        """A period label that exists in the EDH map must not leak to other formats."""
        assert get_meta_value("LE", "Last 2 Weeks") is None

    def test_unknown_period_for_mapped_format_returns_none(self):
        """Unknown period for a mapped format returns None."""
        assert get_meta_value("EDH", "Not A Real Period") is None
