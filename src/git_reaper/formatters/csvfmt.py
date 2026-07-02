"""CSV rendering for the analysis commands, so results feed spreadsheets
and notebooks without ceremony. Deterministic: same result, same bytes."""

from __future__ import annotations

import csv
import io

from git_reaper.models import CensusResult, UnfinishedResult


def render_census(result: CensusResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["extension", "language", "files", "size_bytes", "lines", "token_estimate"])
    for stat in result.extensions:
        writer.writerow(
            [
                stat.extension,
                stat.language,
                stat.files,
                stat.size_bytes,
                stat.line_count,
                stat.token_estimate,
            ]
        )
    return buf.getvalue()


def render_unfinished(result: UnfinishedResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["path", "line", "marker", "text", "author", "age_days"])
    for marker in result.markers:
        writer.writerow(
            [
                marker.path,
                marker.line,
                marker.marker,
                marker.text,
                marker.author or "",
                marker.age_days if marker.age_days is not None else "",
            ]
        )
    return buf.getvalue()
