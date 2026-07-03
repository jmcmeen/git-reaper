"""Schema freeze prep (0.9.0): the shape of every artifact, pinned.

Ascension (1.0.0) promises artifact schemas locked at v1. This golden
registry is the tripwire: adding a command extends it, but renaming or
removing a field on an existing model -- or dropping a command -- is a
BREAKING CHANGE that must wait for a schema version bump (v2), not slip
into a patch. If this test fails, you either update the golden entry AND
bump the artifact schema version, or you revert the field change.

Adding new optional fields is allowed before the freeze; that is why this
pins names, not full JSON schemas.
"""

from __future__ import annotations

import dataclasses

from git_reaper import schemas

#: command -> the exact field names of its result model at schema v1.
FROZEN_FIELDS: dict[str, set[str]] = {
    "harvest": {
        "provenance",
        "root",
        "files",
        "skipped",
        "total_bytes",
        "total_lines",
        "token_estimate",
    },
    "limbs": {"provenance", "root", "dir_count", "file_count", "total_bytes"},
    "conjure": {
        "provenance",
        "root",
        "files",
        "skipped",
        "total_bytes",
        "token_estimate",
        "split_tokens",
        "parts",
        "veiled",
    },
    "reanimate": {"out", "schema", "files", "verify_failures"},
    "census": {
        "provenance",
        "extensions",
        "total_files",
        "total_bytes",
        "total_lines",
        "token_estimate",
    },
    "unfinished": {"provenance", "markers", "counts"},
    "grimoire": {"settings", "recipes", "files"},
    "pulse": {"checks"},
    "banish": {"removed", "kept", "reclaimed_bytes"},
    "chronicle": {"provenance", "commits", "changelog"},
    "souls": {"provenance", "souls", "total_commits", "bus_factor", "heatmap", "witching_hour"},
    "haunt": {"provenance", "hotspots"},
    "autopsy": {
        "provenance",
        "path",
        "exists",
        "created",
        "created_sha",
        "commits",
        "insertions",
        "deletions",
        "authors",
        "former_names",
        "history",
        "blame_lines",
        "oldest_line",
        "newest_line",
        "median_age_days",
    },
    "graveyard": {"provenance", "dead"},
    "resurrect": {"path", "sha", "out", "size_bytes"},
    "ghosts": {"provenance", "branches", "threshold_days"},
    "rot": {"provenance", "files"},
    "tombstone": {
        "provenance",
        "name",
        "born",
        "last",
        "age_days",
        "commits",
        "souls",
        "last_words",
        "witching_hour",
    },
    "exhume": {"provenance", "findings", "blobs_scanned", "suppressed"},
    "veil": {"provenance", "input", "replacements", "total"},
    "omens": {"provenance", "lens", "weights", "omens"},
    "doppelgangers": {"provenance", "clusters", "files_scanned", "reclaimable_bytes"},
    "bloat": {"provenance", "tree", "walls", "tree_bytes", "walls_bytes"},
    "bones": {"provenance", "files", "parsed_files", "skipped_files"},
    "scry": {
        "provenance",
        "ref_a",
        "ref_b",
        "commits",
        "insertions",
        "deletions",
        "files",
        "souls",
        "new_souls",
    },
    "plague": {"provenance", "dependencies", "afflictions", "checked", "unpinned"},
    "necropolis": {"command", "graves", "index"},
    "distill": {
        "provenance",
        "name",
        "profile",
        "description",
        "languages",
        "total_files",
        "layout",
        "tooling",
        "commands",
        "commits_sampled",
        "commit_prefixes",
        "conventional_share",
        "gotchas",
        "bug_themes",
        "marker_counts",
        "owners",
        "bus_factor",
        "bones",
    },
    "scavenge": {"provenance", "out", "skills"},
    "ward": {"provenance", "checks", "policy_source"},
    "leech": {"provenance", "input", "out", "blocks", "skipped"},
    "embalm": {"provenance", "out", "files", "total_bytes", "archive_sha256"},
    "wake": {"provenance", "since", "since_date", "suggested_bump", "commits", "sections"},
    "lineage": {"provenance", "needle", "regex", "path", "commits", "origin"},
    "possession": {"provenance", "threshold", "files", "dirs", "possessed_count"},
    "revenant": {"provenance", "revenants", "offenders", "min_fixes"},
    "prophecy": {"provenance", "horizon_days", "prophecies"},
    "exorcise": {"provenance", "targets", "commands", "warnings"},
    "effigy": {
        "provenance",
        "name",
        "born",
        "last",
        "commits",
        "bus_factor",
        "souls",
        "heatmap",
        "witching_hour",
        "slices",
    },
}


def test_every_registered_command_is_frozen():
    assert set(FROZEN_FIELDS) == set(schemas.COMMAND_MODELS), (
        "a command joined or left the registry; extend (never rewrite) the golden table"
    )


def test_no_model_field_moved_without_a_version_bump():
    for command, model in schemas.COMMAND_MODELS.items():
        fields = {f.name for f in dataclasses.fields(model)}
        assert fields == FROZEN_FIELDS[command], (
            f"{command}: the {model.__name__} fields changed; a rename or removal "
            "is a breaking schema change and needs a schema version bump"
        )


def test_schema_version_is_still_v1():
    # bump this test together with the version, deliberately, never by accident
    assert schemas.SCHEMA_VERSION == "v1"
    assert schemas.artifact_schema("harvest") == "harvest/v1"
