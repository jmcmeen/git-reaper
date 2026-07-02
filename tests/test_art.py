"""Easter eggs: seasonal art with injectable dates."""

from __future__ import annotations

from datetime import date

from git_reaper import art


def test_halloween_banner_only_on_the_night():
    assert art.seasonal_banner(date(2026, 10, 31))
    assert "veil is thin" in (art.seasonal_banner(date(2026, 10, 31)) or "")
    assert art.seasonal_banner(date(2026, 10, 30)) is None
    assert art.seasonal_banner(date(2026, 7, 2)) is None


def test_friday_the_13th_footer():
    assert art.seasonal_footer(date(2026, 2, 13)) == "beware: it is Friday the 13th."
    assert art.seasonal_footer(date(2026, 11, 13)) is not None
    assert art.seasonal_footer(date(2026, 2, 12)) is None  # a mere Thursday
    assert art.seasonal_footer(date(2026, 3, 12)) is None  # a 12th
    assert art.seasonal_footer(date(2026, 10, 13)) is None  # a Tuesday the 13th
