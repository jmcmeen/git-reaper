"""HTML rendering: a self-contained, dark-themed report per command.

One file, zero external requests: styles are inline (the crypt palette from
theme.py, hex-coded because browsers do not speak Rich), the only "chart"
is a CSS bar per row. Deterministic like every other formatter.
"""

from __future__ import annotations

import html
from collections.abc import Callable
from typing import Any

from git_reaper.fsutil import human_size
from git_reaper.models import (
    BloatResult,
    CensusResult,
    ChronicleResult,
    DoppelgangersResult,
    ExhumeResult,
    GhostsResult,
    GraveyardResult,
    HauntResult,
    OmensResult,
    PlagueResult,
    Provenance,
    RotResult,
    ScryResult,
    SoulsResult,
    UnfinishedResult,
)

#: Cell payload: text, or (text, numeric value for the bar column).
Cell = Any
Section = tuple[str, list[str], list[list[Cell]], int | None]

_CSS = """
:root {
  --bone: #ededed; --ash: #7f7f7f; --grave: #5f5faf; --blood: #d70000;
  --necro: #00d700; --eldritch: #875fd7; --ember: #ff8700; --crypt: #121216;
}
body { background: var(--crypt); color: var(--bone); margin: 2rem auto;
  max-width: 72rem; padding: 0 1rem;
  font: 15px/1.5 ui-monospace, "Cascadia Code", "Fira Code", monospace; }
h1 { color: var(--eldritch); font-size: 1.4rem; }
h2 { color: var(--bone); font-size: 1.1rem; margin-top: 2rem; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th { color: var(--ash); text-align: left; font-weight: normal;
  border-bottom: 1px solid var(--grave); padding: .3rem .6rem; }
td { padding: .3rem .6rem; border-bottom: 1px solid #26262e; vertical-align: top; }
td.num { text-align: right; white-space: nowrap; }
tr:hover td { background: #1a1a22; }
.provenance { color: var(--ash); border: 1px solid var(--grave);
  padding: .8rem 1rem; white-space: pre; overflow-x: auto; }
.bar { position: relative; min-width: 8rem; }
.bar span { position: relative; z-index: 1; }
.bar i { position: absolute; left: 0; top: 15%; bottom: 15%;
  background: var(--eldritch); opacity: .35; border-radius: 2px; }
.severity-high { color: var(--blood); }
.severity-medium { color: var(--ember); }
.severity-low { color: var(--ash); }
.footer { color: var(--ash); margin-top: 2rem; }
code { color: var(--necro); }
"""


class Raw(str):
    """A cell that is already safe HTML (built by _severity/_code, never from
    repo content). Everything else gets escaped - a report must not be a
    vector for whatever the scanned files contain."""


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _provenance_block(prov: Provenance, kind: str) -> str:
    lines = [f"git-reaper {kind}", f"schema:    {prov.schema}", f"source:    {prov.source}"]
    if prov.ref or prov.sha:
        at = f" @ {prov.sha[:7]}" if prov.sha else ""
        lines.append(f"ref:       {prov.ref or 'HEAD'}{at}")
    lines += [
        f"generated: {prov.generated}",
        f"tool:      git-reaper {prov.tool_version}",
        f"invoked:   {prov.invoked}",
    ]
    return "<div class=\"provenance\">" + _esc("\n".join(lines)) + "</div>"


def _cell_html(cell: Cell, bar: bool, peak: float) -> str:
    if isinstance(cell, tuple):
        text, value = cell
        if bar and peak > 0:
            width = max(1.0, 100.0 * float(value) / peak)
            return (
                f'<td class="num bar"><i style="width:{width:.1f}%"></i>'
                f"<span>{_esc(text)}</span></td>"
            )
        return f'<td class="num">{_esc(text)}</td>'
    if isinstance(cell, Raw):
        return f"<td>{cell}</td>"
    return f"<td>{_esc(cell)}</td>"


def _table(headers: list[str], rows: list[list[Cell]], bar_col: int | None) -> str:
    peak = 0.0
    if bar_col is not None:
        for row in rows:
            cell = row[bar_col]
            if isinstance(cell, tuple):
                peak = max(peak, float(cell[1]))
    parts = ["<table><thead><tr>"]
    parts += [f"<th>{_esc(h)}</th>" for h in headers]
    parts.append("</tr></thead><tbody>")
    for row in rows:
        parts.append("<tr>")
        parts += [
            _cell_html(cell, bar=(i == bar_col), peak=peak) for i, cell in enumerate(row)
        ]
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def _page(title: str, prov: Provenance, kind: str, sections: list[Section], footer: str) -> str:
    body = [f"<h1>git-reaper {_esc(title)}</h1>", _provenance_block(prov, kind)]
    for heading, headers, rows, bar_col in sections:
        if heading:
            body.append(f"<h2>{_esc(heading)}</h2>")
        body.append(_table(headers, rows, bar_col))
    body.append(f'<div class="footer">{_esc(footer)}</div>')
    return (
        "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>git-reaper {_esc(title)}</title>"
        f"<style>{_CSS}</style></head>\n<body>\n" + "\n".join(body) + "\n</body></html>\n"
    )


def _num(value: Any, text: str | None = None) -> tuple[str, float]:
    return (text if text is not None else f"{value:,}", float(value))


def _severity(level: str) -> Raw:
    return Raw(f'<span class="severity-{_esc(level)}">{_esc(level)}</span>')


def _code(text: str) -> Raw:
    return Raw(f"<code>{_esc(text)}</code>")


# -- per-command sections ----------------------------------------------------


def _census_sections(result: CensusResult) -> tuple[list[Section], str]:
    rows = [
        [
            stat.extension,
            stat.language,
            _num(stat.files),
            _num(stat.size_bytes, human_size(stat.size_bytes)),
            _num(stat.line_count),
            _num(stat.token_estimate),
        ]
        for stat in result.extensions
    ]
    footer = (
        f"{result.total_files} files, {human_size(result.total_bytes)}, "
        f"{result.total_lines:,} lines, ~{result.token_estimate:,} tokens (chars/4)"
    )
    return [("", ["extension", "language", "files", "size", "lines", "~tokens"], rows, 3)], footer


def _unfinished_sections(result: UnfinishedResult) -> tuple[list[Section], str]:
    rows = [
        [
            marker.marker,
            f"{marker.path}:{marker.line}",
            marker.text,
            marker.author or "",
            f"{marker.age_days}d" if marker.age_days is not None else "",
        ]
        for marker in result.markers
    ]
    tally = ", ".join(f"{k}: {v}" for k, v in sorted(result.counts.items()))
    return [("", ["marker", "where", "text", "author", "age"], rows, None)], (
        f"{len(result.markers)} markers ({tally})" if result.markers else "nothing unfinished."
    )


def _chronicle_sections(result: ChronicleResult) -> tuple[list[Section], str]:
    headers = ["sha", "date", "author", "message", "files", "+ins", "-del"]
    sections: list[Section] = []
    if result.changelog:
        for section in result.changelog:
            title = section.tag if section.date is None else f"{section.tag} ({section.date})"
            rows = [
                [_code(c.sha[:7]), c.date, c.author, c.message, _num(c.files_changed),
                 _num(c.insertions), _num(c.deletions)]
                for c in section.commits
            ]
            sections.append((title, headers, rows, 5))
    else:
        rows = [
            [_code(c.sha[:7]), c.date, c.author, c.message, _num(c.files_changed),
             _num(c.insertions), _num(c.deletions)]
            for c in result.commits
        ]
        sections.append(("", headers, rows, 5))
    return sections, f"{len(result.commits)} commits"


def _souls_sections(result: SoulsResult) -> tuple[list[Section], str]:
    rows = [
        [s.name, s.email, _num(s.commits), _num(s.insertions), _num(s.deletions),
         s.first_seen, s.last_seen]
        for s in result.souls
    ]
    footer = (
        f"{len(result.souls)} souls, {result.total_commits} commits, "
        f"bus factor {result.bus_factor}"
        + (f", witching hour {result.witching_hour}" if result.witching_hour else "")
    )
    headers = ["soul", "email", "commits", "+ins", "-del", "first seen", "last seen"]
    return [("", headers, rows, 2)], footer


def _haunt_sections(result: HauntResult) -> tuple[list[Section], str]:
    rows = [
        [h.path, _num(h.commits), _num(h.churn), _num(h.insertions), _num(h.deletions)]
        for h in result.hotspots
    ]
    return [("", ["file", "commits", "churn", "+ins", "-del"], rows, 2)], (
        f"{len(result.hotspots)} hotspots"
    )


def _graveyard_sections(result: GraveyardResult) -> tuple[list[Section], str]:
    rows = [[d.path, d.died, _code(d.last_sha[:7]), d.author] for d in result.dead]
    return [("", ["dead file", "died", "fatal commit", "author"], rows, None)], (
        f"{len(result.dead)} dead"
    )


def _ghosts_sections(result: GhostsResult) -> tuple[list[Section], str]:
    rows = []
    for b in result.branches:
        flags = ", ".join(
            f for f, on in (("merged", b.merged), ("gone", b.gone_upstream), ("stale", b.stale))
            if on
        )
        rows.append([b.name, b.last_commit, _num(b.age_days, f"{b.age_days}d"), b.author, flags])
    return [("", ["branch", "last commit", "age", "author", "flags"], rows, 2)], (
        f"{len(result.branches)} branches"
    )


def _rot_sections(result: RotResult) -> tuple[list[Section], str]:
    rows = [
        [f.path, f.last_commit, _num(f.age_days, f"{f.age_days}d"), _code(f.last_sha[:7])]
        for f in result.files
    ]
    return [("", ["file", "last touched", "age", "last commit"], rows, 2)], (
        f"{len(result.files)} files"
    )


def _exhume_sections(result: ExhumeResult) -> tuple[list[Section], str]:
    rows = [
        [
            _severity(f.severity),
            f.rule,
            f"{f.path}:{f.line}",
            Raw(_code(f.preview) + " (masked)"),
            _code(f.sha[:7]) if f.sha else "",
            f.author,
        ]
        for f in result.findings
    ]
    footer = (
        f"{len(result.findings)} findings, {result.blobs_scanned} blobs scanned, "
        f"{result.suppressed} baselined"
    )
    headers = ["severity", "rule", "where", "preview", "commit", "author"]
    return [("", headers, rows, None)], footer


def _omens_sections(result: OmensResult) -> tuple[list[Section], str]:
    rows = [
        [
            _num(o.score, f"{o.score:.3f}"),
            o.path,
            f"{o.churn_score:.2f}",
            f"{o.bug_score:.2f}",
            f"{o.age_score:.2f}",
            f"{o.size_score:.2f}",
            _num(o.commits),
        ]
        for o in result.omens
    ]
    weights = " ".join(f"{k}={v:g}" for k, v in result.weights.items())
    footer = f"lens: {result.lens}; weights: {weights}. omens are hints, not fate."
    headers = ["omen", "file", "churn", "bugs", "age", "size", "commits"]
    return [("", headers, rows, 0)], footer


def _doppelgangers_sections(result: DoppelgangersResult) -> tuple[list[Section], str]:
    rows = []
    for cluster in result.clusters:
        rows.append(
            [
                Raw("<br>".join(_esc(p) for p in cluster.paths)),
                _num(len(cluster.paths)),
                _num(cluster.size_bytes, human_size(cluster.size_bytes)),
                _num(cluster.reclaimable_bytes, human_size(cluster.reclaimable_bytes)),
            ]
        )
    footer = (
        f"{len(result.clusters)} clusters in {result.files_scanned} files, "
        f"{human_size(result.reclaimable_bytes)} reclaimable"
    )
    return [("", ["paths", "copies", "size", "reclaimable"], rows, 3)], footer


def _bloat_sections(result: BloatResult) -> tuple[list[Section], str]:
    sections: list[Section] = [
        (
            "the living",
            ["file", "size"],
            [[e.path, _num(e.size_bytes, human_size(e.size_bytes))] for e in result.tree],
            1,
        )
    ]
    if result.walls:
        sections.append(
            (
                "the walls (blobs gone from the tree, not from .git)",
                ["last known as", "size", "blob"],
                [
                    [e.path, _num(e.size_bytes, human_size(e.size_bytes)), _code(e.sha[:7])]
                    for e in result.walls
                ],
                1,
            )
        )
    footer = f"working tree {human_size(result.tree_bytes)}"
    if result.walls:
        footer += f"; still in the walls {human_size(result.walls_bytes)}"
    return sections, footer


def _scry_sections(result: ScryResult) -> tuple[list[Section], str]:
    sections: list[Section] = [
        (
            f"{result.ref_a} .. {result.ref_b}",
            ["file", "commits", "+ins", "-del"],
            [
                [d.path, _num(d.commits), _num(d.insertions), _num(d.deletions)]
                for d in result.files
            ],
            1,
        ),
        (
            "hands",
            ["soul", "commits"],
            [[s.author, _num(s.commits)] for s in result.souls],
            1,
        ),
    ]
    footer = f"{result.commits} commits, +{result.insertions}/-{result.deletions}"
    if result.new_souls:
        footer += f"; new souls: {', '.join(result.new_souls)}"
    return sections, footer


def _plague_sections(result: PlagueResult) -> tuple[list[Section], str]:
    sections: list[Section] = []
    if result.afflictions:
        sections.append(
            (
                "afflictions",
                ["id", "package", "version", "ecosystem", "summary"],
                [[a.id, a.package, a.version, a.ecosystem, a.summary] for a in result.afflictions],
                None,
            )
        )
    sections.append(
        (
            "dependencies",
            ["package", "version", "ecosystem", "manifest", "pinned"],
            [
                [d.name, d.version or "(range)", d.ecosystem, d.manifest,
                 "yes" if d.pinned else "no"]
                for d in result.dependencies
            ],
            None,
        )
    )
    footer = (
        f"{len(result.afflictions)} afflictions across {len(result.dependencies)} dependencies"
        if result.checked
        else "offline: manifests parsed, the oracle was not consulted"
    )
    return sections, footer


_RENDERERS: dict[str, Callable[[Any], tuple[list[Section], str]]] = {
    "census": _census_sections,
    "unfinished": _unfinished_sections,
    "chronicle": _chronicle_sections,
    "souls": _souls_sections,
    "haunt": _haunt_sections,
    "graveyard": _graveyard_sections,
    "ghosts": _ghosts_sections,
    "rot": _rot_sections,
    "exhume": _exhume_sections,
    "omens": _omens_sections,
    "doppelgangers": _doppelgangers_sections,
    "bloat": _bloat_sections,
    "scry": _scry_sections,
    "plague": _plague_sections,
}

#: Commands `--format html` supports (the CLI checks membership).
SUPPORTED = frozenset(_RENDERERS)


def render(command: str, result: Any) -> str:
    """One self-contained dark HTML report for a command's result."""
    sections, footer = _RENDERERS[command](result)
    return _page(command, result.provenance, command, sections, footer)
