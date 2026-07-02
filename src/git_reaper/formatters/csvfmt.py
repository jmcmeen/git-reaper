"""CSV rendering for the analysis commands, so results feed spreadsheets
and notebooks without ceremony. Deterministic: same result, same bytes."""

from __future__ import annotations

import csv
import io

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
    RotResult,
    ScryResult,
    SoulsResult,
    UnfinishedResult,
)


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


def render_chronicle(result: ChronicleResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        ["sha", "date", "author", "email", "message", "files_changed", "insertions", "deletions"]
    )
    for c in result.commits:
        writer.writerow(
            [
                c.sha,
                c.date,
                c.author,
                c.email,
                c.message,
                c.files_changed,
                c.insertions,
                c.deletions,
            ]
        )
    return buf.getvalue()


def render_souls(result: SoulsResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        ["name", "email", "commits", "insertions", "deletions", "first_seen", "last_seen"]
    )
    for s in result.souls:
        writer.writerow(
            [s.name, s.email, s.commits, s.insertions, s.deletions, s.first_seen, s.last_seen]
        )
    return buf.getvalue()


def render_haunt(result: HauntResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["path", "commits", "churn", "insertions", "deletions"])
    for h in result.hotspots:
        writer.writerow([h.path, h.commits, h.churn, h.insertions, h.deletions])
    return buf.getvalue()


def render_graveyard(result: GraveyardResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["path", "died", "last_sha", "author"])
    for d in result.dead:
        writer.writerow([d.path, d.died, d.last_sha, d.author])
    return buf.getvalue()


def render_ghosts(result: GhostsResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        ["name", "last_commit", "age_days", "author", "merged", "gone_upstream", "stale"]
    )
    for b in result.branches:
        writer.writerow(
            [b.name, b.last_commit, b.age_days, b.author, b.merged, b.gone_upstream, b.stale]
        )
    return buf.getvalue()


def render_rot(result: RotResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["path", "last_commit", "age_days", "last_sha"])
    for f in result.files:
        writer.writerow([f.path, f.last_commit, f.age_days, f.last_sha])
    return buf.getvalue()


def render_exhume(result: ExhumeResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        ["severity", "rule", "path", "line", "preview", "sha", "date", "author", "fingerprint"]
    )
    for f in result.findings:
        writer.writerow(
            [f.severity, f.rule, f.path, f.line, f.preview, f.sha, f.date, f.author, f.fingerprint]
        )
    return buf.getvalue()


def render_omens(result: OmensResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        [
            "path",
            "score",
            "churn_score",
            "bug_score",
            "age_score",
            "size_score",
            "commits",
            "churn",
            "bug_commits",
            "age_days",
            "size_bytes",
        ]
    )
    for o in result.omens:
        writer.writerow(
            [
                o.path,
                o.score,
                o.churn_score,
                o.bug_score,
                o.age_score,
                o.size_score,
                o.commits,
                o.churn,
                o.bug_commits,
                o.age_days,
                o.size_bytes,
            ]
        )
    return buf.getvalue()


def render_doppelgangers(result: DoppelgangersResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["sha256", "size_bytes", "copies", "reclaimable_bytes", "path"])
    for cluster in result.clusters:
        for path in cluster.paths:
            writer.writerow(
                [
                    cluster.sha256,
                    cluster.size_bytes,
                    len(cluster.paths),
                    cluster.reclaimable_bytes,
                    path,
                ]
            )
    return buf.getvalue()


def render_bloat(result: BloatResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["where", "path", "size_bytes", "sha"])
    for entry in result.tree:
        writer.writerow(["tree", entry.path, entry.size_bytes, ""])
    for entry in result.walls:
        writer.writerow(["walls", entry.path, entry.size_bytes, entry.sha])
    return buf.getvalue()


def render_scry(result: ScryResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["path", "commits", "insertions", "deletions"])
    for delta in result.files:
        writer.writerow([delta.path, delta.commits, delta.insertions, delta.deletions])
    return buf.getvalue()


def render_plague(result: PlagueResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["package", "version", "ecosystem", "manifest", "pinned", "afflictions"])
    by_package: dict[tuple[str, str], list[str]] = {}
    for a in result.afflictions:
        by_package.setdefault((a.package, a.version), []).append(a.id)
    for dep in result.dependencies:
        ids = by_package.get((dep.name, dep.version or ""), [])
        writer.writerow(
            [dep.name, dep.version or "", dep.ecosystem, dep.manifest, dep.pinned, " ".join(ids)]
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
