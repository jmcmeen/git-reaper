"""SVG rendering: the effigy poster.

Self-contained (no external fonts, scripts, or fetches -- the same rule as
the HTML reports), deterministic (layout is arithmetic over the result, no
randomness, no clocks), and drawn in the crypt's own palette. The provenance
rides along as an XML comment so even the poster is citable.
"""

from __future__ import annotations

import math
from xml.sax.saxutils import escape, quoteattr

from git_reaper.formatters.markdown import render_provenance
from git_reaper.fsutil import human_size
from git_reaper.models import EffigyResult

_W, _H = 920, 700
_BG = "#16121f"  # the crypt at night
_PANEL = "#201a2e"
_BONE = "#e8e4d8"
_ASH = "#8a8496"
_NECRO = "#50fa7b"
_ELDRITCH = "#bd93f9"
_EMBER = "#ffb86c"
_GRAVE = "#44475a"
_FONT = "ui-monospace, 'Cascadia Code', Menlo, Consolas, monospace"

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _text(
    x: float, y: float, content: str, size: int = 14, fill: str = _BONE, anchor: str = "start"
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{_FONT}" font-size="{size}" '
        f'fill="{fill}" text-anchor="{anchor}">{escape(content)}</text>'
    )


def render_effigy(result: EffigyResult) -> str:
    """The whole poster: header, constellation, heatmap, treemap strip."""
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_W}" height="{_H}" '
        f'viewBox="0 0 {_W} {_H}" role="img" '
        f"aria-label={quoteattr('effigy of ' + result.name)}>",
        # a comment cannot hold the stamp (flags carry "--"), so a <desc> does
        "<desc>\n" + escape(render_provenance(result.provenance, "effigy")) + "</desc>",
        f'<rect width="{_W}" height="{_H}" fill="{_BG}"/>',
    ]
    parts.extend(_header(result))
    parts.extend(_constellation(result, cx=250.0, cy=300.0, radius=140.0))
    parts.extend(_heatmap(result, x=470.0, y=180.0))
    parts.extend(_treemap(result, x=40.0, y=510.0, width=_W - 80.0, height=120.0))
    parts.append(_text(_W / 2, _H - 18, "raised by git-reaper effigy", 11, _ASH, anchor="middle"))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _header(result: EffigyResult) -> list[str]:
    years = f"{result.born[:4]} - {result.last[:4]}"
    vitals = (
        f"{result.commits:,} commits   {len(result.souls)} souls shown   "
        f"bus factor {result.bus_factor}"
        + (f"   haunted {result.witching_hour}" if result.witching_hour else "")
    )
    return [
        _text(_W / 2, 52, result.name, 34, _ELDRITCH, anchor="middle"),
        _text(_W / 2, 82, years, 18, _ASH, anchor="middle"),
        _text(_W / 2, 110, vitals, 14, _BONE, anchor="middle"),
        f'<line x1="40" y1="130" x2="{_W - 40}" y2="130" stroke="{_GRAVE}" stroke-width="1"/>',
    ]


def _constellation(result: EffigyResult, cx: float, cy: float, radius: float) -> list[str]:
    """Souls as stars on a ring, sized by their share of the commits."""
    parts = [_text(cx, cy - radius - 24, "the constellation", 15, _EMBER, anchor="middle")]
    souls = result.souls
    if not souls:
        return parts
    peak = max(s.commits for s in souls)
    for i, soul in enumerate(souls):
        angle = -math.pi / 2 + (2 * math.pi * i) / len(souls)
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        r = 6 + 18 * math.sqrt(soul.commits / peak) if peak else 6
        parts.append(
            f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y:.1f}" '
            f'stroke="{_GRAVE}" stroke-width="1"/>'
        )
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{_ELDRITCH}" '
            f'fill-opacity="0.75" stroke="{_BONE}" stroke-width="1"/>'
        )
        label_y = y + r + 14 if y >= cy else y - r - 6
        parts.append(_text(x, label_y, soul.name, 11, _BONE, anchor="middle"))
        parts.append(_text(x, label_y + 12, f"{soul.commits}", 10, _ASH, anchor="middle"))
    parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3" fill="{_NECRO}"/>')
    return parts


def _heatmap(result: EffigyResult, x: float, y: float) -> list[str]:
    """The 7x24 activity grid, necro-green by intensity."""
    cell, gap = 16.0, 2.0
    parts = [_text(x, y - 14, "the witching hours", 15, _EMBER)]
    grid = result.heatmap
    peak = max((max(row) for row in grid), default=0)
    for day in range(7):
        parts.append(
            _text(x - 8, y + day * (cell + gap) + cell - 3, _WEEKDAYS[day], 10, _ASH, "end")
        )
        for hour in range(24):
            count = grid[day][hour]
            opacity = 0.08 if not count or not peak else 0.15 + 0.85 * (count / peak)
            parts.append(
                f'<rect x="{x + hour * (cell + gap):.1f}" y="{y + day * (cell + gap):.1f}" '
                f'width="{cell}" height="{cell}" rx="2" fill="{_NECRO}" '
                f'fill-opacity="{opacity:.2f}"/>'
            )
    for hour in (0, 6, 12, 18, 23):
        parts.append(
            _text(
                x + hour * (cell + gap) + cell / 2,
                y + 7 * (cell + gap) + 12,
                f"{hour:02d}",
                10,
                _ASH,
                "middle",
            )
        )
    return parts


def _treemap(result: EffigyResult, x: float, y: float, width: float, height: float) -> list[str]:
    """A one-row treemap strip: top-level directories by weight."""
    parts = [_text(x, y - 10, "the estate (bytes by directory)", 15, _EMBER)]
    total = sum(s.size_bytes for s in result.slices)
    if not total:
        return parts
    shades = (_ELDRITCH, _NECRO, _EMBER, "#ff79c6", "#8be9fd", "#f1fa8c")
    cursor = x
    for i, piece in enumerate(result.slices):
        w = width * piece.size_bytes / total
        parts.append(
            f'<rect x="{cursor:.1f}" y="{y:.1f}" width="{max(w - 2, 1):.1f}" '
            f'height="{height:.1f}" rx="3" fill="{shades[i % len(shades)]}" '
            f'fill-opacity="0.55" stroke="{_GRAVE}"/>'
        )
        if w > 60:
            parts.append(_text(cursor + 8, y + 24, piece.name, 12, _BONE))
            parts.append(_text(cursor + 8, y + 42, human_size(piece.size_bytes), 10, _ASH))
        cursor += w
    return parts
