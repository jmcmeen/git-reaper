"""File-type census: what is buried here, and how much of it.

Great for sizing a repo before conjuring it. Binary files are counted and
weighed but their lines are not (there are no lines in a corpse).
"""

from __future__ import annotations

from pathlib import Path

from git_reaper import fsutil
from git_reaper.core.provenance import make_provenance
from git_reaper.ignore import IgnoreMatcher, walk_files
from git_reaper.models import CensusResult, ExtensionStat, RepoRef
from git_reaper.schemas import artifact_schema

#: Extension -> language label. Small on purpose; unknown is fine.
LANGUAGES = {
    ".c": "C",
    ".cfg": "Config",
    ".cpp": "C++",
    ".cs": "C#",
    ".css": "CSS",
    ".go": "Go",
    ".h": "C header",
    ".html": "HTML",
    ".ini": "Config",
    ".java": "Java",
    ".js": "JavaScript",
    ".json": "JSON",
    ".jsx": "JavaScript",
    ".kt": "Kotlin",
    ".lua": "Lua",
    ".md": "Markdown",
    ".php": "PHP",
    ".pl": "Perl",
    ".py": "Python",
    ".r": "R",
    ".rb": "Ruby",
    ".rs": "Rust",
    ".sh": "Shell",
    ".sql": "SQL",
    ".swift": "Swift",
    ".toml": "TOML",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".txt": "Text",
    ".xml": "XML",
    ".yaml": "YAML",
    ".yml": "YAML",
}


def census(
    repo: RepoRef,
    excludes: list[str] | None = None,
    invoked: str = "reaper census",
    generated: str | None = None,
) -> CensusResult:
    """Count and weigh every non-ignored file, grouped by extension."""
    root = Path(repo.path)
    matcher = IgnoreMatcher(root, extra_excludes=excludes)
    result = CensusResult(
        provenance=make_provenance(artifact_schema("census"), repo, invoked, generated)
    )

    stats: dict[str, ExtensionStat] = {}
    for path in walk_files(root, matcher):
        ext = path.suffix.lower() or "(none)"
        stat = stats.get(ext)
        if stat is None:
            stat = stats[ext] = ExtensionStat(extension=ext, language=LANGUAGES.get(ext, ""))
        size = path.stat().st_size
        stat.files += 1
        stat.size_bytes += size
        result.total_files += 1
        result.total_bytes += size
        if not fsutil.is_binary(path):
            lines = fsutil.count_lines(path)
            stat.line_count += lines
            stat.token_estimate += fsutil.estimate_tokens(size)
            result.total_lines += lines
            result.token_estimate += fsutil.estimate_tokens(size)

    result.extensions = sorted(stats.values(), key=lambda s: (-s.size_bytes, s.extension))
    result.provenance.files = result.total_files
    result.provenance.token_estimate = result.token_estimate
    return result
