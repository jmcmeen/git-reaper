"""The gallery's invariants, plus seasonal easter eggs with injectable dates."""

from __future__ import annotations

from datetime import date

import pytest

from git_reaper import art


def _every_piece() -> list[str]:
    return [art.piece(name) for name in (*art.gallery(), "jack-o-lantern")]


def test_the_gallery_is_hung():
    # the pool exists and the star of the show is in it
    assert "grim-reaper" in art.gallery()
    assert len(art.gallery()) >= 5


def test_every_piece_fits_a_terminal():
    # the brief's guiding rule: 60 columns max, banner heights stay sane
    for piece in _every_piece():
        assert all(len(line) <= 60 for line in piece.splitlines()), piece
        assert len(piece.splitlines()) <= 26, piece


def test_every_piece_is_rich_markup_safe():
    # pieces are interpolated into [eldritch]...[/eldritch] markup
    for piece in _every_piece():
        assert "[" not in piece and "]" not in piece, piece


def test_pieces_have_no_margins_or_trailing_space():
    # loader contract: content is exact, no surrounding blank lines
    for piece in _every_piece():
        assert piece == piece.strip("\n"), piece


def test_boo_draws_from_the_gallery():
    assert art.boo() in {art.piece(name) for name in art.gallery()}


def test_unknown_piece_raises():
    with pytest.raises(KeyError):
        art.piece("banshee")


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
