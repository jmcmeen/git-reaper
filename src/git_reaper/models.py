"""Result models. Every core function returns these, never formatted strings.

Formatting is a separate layer (formatters/); the CLI and TUI only present.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SourceKind = Literal["local", "remote"]


@dataclass
class RepoRef:
    """Where the data came from: a local path or a remote clone."""

    source: str
    kind: SourceKind
    path: str
    ref: str | None = None
    sha: str | None = None


@dataclass
class Provenance:
    """Stamp carried by every combined or packed artifact."""

    schema: str
    source: str
    ref: str | None
    sha: str | None
    generated: str
    tool_version: str
    invoked: str
    files: int = 0
    token_estimate: int = 0


@dataclass
class FileEntry:
    """One file the reaper looked at. Paths are POSIX-style and relative."""

    path: str
    size_bytes: int = 0
    line_count: int = 0
    skipped: bool = False
    skip_reason: str | None = None


@dataclass
class HarvestResult:
    """The flagship: gathered files ready to be concatenated."""

    provenance: Provenance
    root: str
    files: list[FileEntry] = field(default_factory=list)
    skipped: list[FileEntry] = field(default_factory=list)
    total_bytes: int = 0
    total_lines: int = 0
    token_estimate: int = 0


@dataclass
class TreeNode:
    """One node in a hierarchical listing."""

    name: str
    path: str
    is_dir: bool
    size_bytes: int = 0
    line_count: int = 0
    children: list[TreeNode] = field(default_factory=list)


@dataclass
class TreeResult:
    """A hierarchical file listing. Works on any folder, git or not."""

    provenance: Provenance
    root: TreeNode
    dir_count: int = 0
    file_count: int = 0
    total_bytes: int = 0


@dataclass
class PackedFile:
    """One file inlined into a conjured bundle."""

    path: str
    size_bytes: int = 0
    line_count: int = 0
    token_estimate: int = 0
    fence_len: int = 3
    nonce: int | None = None
    no_eol: bool = False
    sha256: str | None = None


@dataclass
class PackResult:
    """A repo conjured into an LLM-ingestible bundle."""

    provenance: Provenance
    root: str
    files: list[PackedFile] = field(default_factory=list)
    skipped: list[FileEntry] = field(default_factory=list)
    total_bytes: int = 0
    token_estimate: int = 0
    split_tokens: int | None = None
    parts: int = 1
    veiled: int = 0  # replacements made by --veil (0 when unveiled)


@dataclass
class ReanimatedFile:
    """One file reconstructed from a conjured bundle."""

    path: str
    size_bytes: int = 0
    verified: bool | None = None  # None: no hash in the artifact


@dataclass
class ReanimateResult:
    """The inverse of conjure: what rose from the artifact."""

    out: str
    schema: str | None = None  # the artifact's schema line, when present
    files: list[ReanimatedFile] = field(default_factory=list)
    verify_failures: list[str] = field(default_factory=list)


@dataclass
class ExtensionStat:
    """Census row: one file extension."""

    extension: str
    language: str
    files: int = 0
    size_bytes: int = 0
    line_count: int = 0
    token_estimate: int = 0


@dataclass
class CensusResult:
    """File-type census: what is buried here, and how much of it."""

    provenance: Provenance
    extensions: list[ExtensionStat] = field(default_factory=list)
    total_files: int = 0
    total_bytes: int = 0
    total_lines: int = 0
    token_estimate: int = 0


@dataclass
class Marker:
    """One TODO/FIXME/HACK/XXX haunting the codebase."""

    path: str
    line: int
    marker: str
    text: str
    author: str | None = None
    age_days: int | None = None


@dataclass
class UnfinishedResult:
    """Every unfinished thing the scan turned up."""

    provenance: Provenance
    markers: list[Marker] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


@dataclass
class ConfigValue:
    """One effective grimoire setting and where it came from."""

    key: str
    value: str
    source: str  # "default", "pyproject", ".reaperrc", or "env NAME"


@dataclass
class Recipe:
    """A named bundle of flags stored in the grimoire."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    description: str = ""
    source: str = ""


@dataclass
class GrimoireResult:
    """Effective configuration: values, origins, and stored recipes."""

    settings: list[ConfigValue] = field(default_factory=list)
    recipes: list[Recipe] = field(default_factory=list)
    files: list[str] = field(default_factory=list)  # config files consulted


@dataclass
class PulseCheck:
    """One signs-of-life check."""

    name: str
    ok: bool
    detail: str


@dataclass
class PulseResult:
    """Doctor report: is this corpse fit for necromancy?"""

    checks: list[PulseCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)


@dataclass
class CommitEntry:
    """One commit in the chronicle."""

    sha: str
    author: str
    email: str
    date: str
    message: str
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0


@dataclass
class ChangelogSection:
    """Commits gathered under one tag (or the unreleased head)."""

    tag: str
    date: str | None
    commits: list[CommitEntry] = field(default_factory=list)


@dataclass
class ChronicleResult:
    """Commit history, newest first, optionally grouped into a changelog."""

    provenance: Provenance
    commits: list[CommitEntry] = field(default_factory=list)
    changelog: list[ChangelogSection] = field(default_factory=list)


@dataclass
class Soul:
    """One contributor's ledger."""

    name: str
    email: str
    commits: int = 0
    insertions: int = 0
    deletions: int = 0
    first_seen: str = ""
    last_seen: str = ""


@dataclass
class SoulsResult:
    """Contributor stats, a bus-factor estimate, and an optional heatmap."""

    provenance: Provenance
    souls: list[Soul] = field(default_factory=list)
    total_commits: int = 0
    bus_factor: int = 0
    # 7 rows (Mon..Sun) x 24 cols of commit counts, by the commit's recorded tz.
    heatmap: list[list[int]] | None = None
    witching_hour: str | None = None  # e.g. "Fri 02:00"


@dataclass
class Hotspot:
    """One file ranked by how often it changes and how much."""

    path: str
    commits: int = 0
    insertions: int = 0
    deletions: int = 0
    churn: int = 0  # insertions + deletions


@dataclass
class HauntResult:
    """Code churn and hotspots: the classic bug-risk proxy."""

    provenance: Provenance
    hotspots: list[Hotspot] = field(default_factory=list)


@dataclass
class AuthorShare:
    """One author's slice of a single file's history."""

    author: str
    commits: int = 0


@dataclass
class AutopsyResult:
    """Deep single-file examination."""

    provenance: Provenance
    path: str
    exists: bool = True
    created: str = ""
    created_sha: str = ""
    commits: int = 0
    insertions: int = 0
    deletions: int = 0
    authors: list[AuthorShare] = field(default_factory=list)
    former_names: list[str] = field(default_factory=list)
    history: list[CommitEntry] = field(default_factory=list)
    # blame-based line-age summary (None when the file cannot be blamed)
    blame_lines: int | None = None
    oldest_line: str | None = None
    newest_line: str | None = None
    median_age_days: int | None = None


@dataclass
class DeadFile:
    """A file that lived and died: path, fatal commit, and its author."""

    path: str
    last_sha: str
    died: str
    author: str


@dataclass
class GraveyardResult:
    """Every file that ever lived and died in the repo."""

    provenance: Provenance
    dead: list[DeadFile] = field(default_factory=list)


@dataclass
class ResurrectResult:
    """A dead file brought back from the graveyard."""

    path: str
    sha: str  # the commit the content was read from (parent of the deletion)
    out: str
    size_bytes: int = 0


@dataclass
class Branch:
    """One branch's hygiene report."""

    name: str
    last_commit: str
    last_sha: str
    author: str
    age_days: int = 0
    merged: bool = False
    gone_upstream: bool = False
    stale: bool = False


@dataclass
class GhostsResult:
    """Branch hygiene: activity, merged-but-undeleted, gone remotes."""

    provenance: Provenance
    branches: list[Branch] = field(default_factory=list)
    threshold_days: int | None = None


@dataclass
class StaleFile:
    """One file ranked by how long it has gone untouched."""

    path: str
    last_commit: str
    last_sha: str
    age_days: int = 0


@dataclass
class RotResult:
    """Staleness report: files untouched the longest."""

    provenance: Provenance
    files: list[StaleFile] = field(default_factory=list)


@dataclass
class TombstoneResult:
    """A stats card for demos and READMEs."""

    provenance: Provenance
    name: str
    born: str = ""
    last: str = ""
    age_days: int = 0
    commits: int = 0
    souls: int = 0
    last_words: str = ""
    witching_hour: str | None = None


@dataclass
class SecretFinding:
    """One secret the exhumation turned up. Never carries the full secret."""

    rule: str
    severity: str  # "low", "medium", or "high"
    path: str
    line: int
    preview: str  # masked: first/last 4 chars only
    fingerprint: str  # sha256 of rule + secret; safe to store in a baseline
    sha: str = ""  # commit that introduced it ("" when unattributed)
    date: str = ""
    author: str = ""


@dataclass
class ExhumeResult:
    """Secrets dug out of the full history."""

    provenance: Provenance
    findings: list[SecretFinding] = field(default_factory=list)
    blobs_scanned: int = 0
    suppressed: int = 0  # findings silenced by the baseline


@dataclass
class VeilCount:
    """How many times one rule fired during a veiling."""

    rule: str
    count: int = 0


@dataclass
class VeilResult:
    """A redaction pass: what was hidden, never what it was."""

    provenance: Provenance
    input: str  # the artifact that was veiled ("-" for stdin)
    replacements: list[VeilCount] = field(default_factory=list)
    total: int = 0


@dataclass
class Omen:
    """One file's risk prophecy. Scores are 0..1; omens are hints, not fate."""

    path: str
    score: float
    churn_score: float = 0.0
    bug_score: float = 0.0
    age_score: float = 0.0
    size_score: float = 0.0
    commits: int = 0
    churn: int = 0
    bug_commits: int = 0
    age_days: int = 0
    size_bytes: int = 0


@dataclass
class OmensResult:
    """Composite per-file risk, ranked most-cursed first."""

    provenance: Provenance
    lens: str = "all"
    weights: dict[str, float] = field(default_factory=dict)
    omens: list[Omen] = field(default_factory=list)


@dataclass
class CloneCluster:
    """Files that are byte-for-byte the same soul in different bodies."""

    sha256: str
    size_bytes: int
    paths: list[str] = field(default_factory=list)
    reclaimable_bytes: int = 0  # (copies - 1) * size


@dataclass
class DoppelgangersResult:
    """Duplicate files by content hash."""

    provenance: Provenance
    clusters: list[CloneCluster] = field(default_factory=list)
    files_scanned: int = 0
    reclaimable_bytes: int = 0


@dataclass
class BloatEntry:
    """One heavy body: a working-tree file or a blob still in the walls."""

    path: str
    size_bytes: int
    sha: str = ""  # blob sha for history entries
    in_tree: bool = True


@dataclass
class BloatResult:
    """The largest files, and the blobs deleted from the tree but not the past."""

    provenance: Provenance
    tree: list[BloatEntry] = field(default_factory=list)
    walls: list[BloatEntry] = field(default_factory=list)  # dead blobs weighing down .git
    tree_bytes: int = 0
    walls_bytes: int = 0


@dataclass
class SkeletonEntry:
    """One structural bone: an import, class, function, or method."""

    kind: str  # "import", "class", "function", or "method"
    name: str
    signature: str
    line: int
    doc: str = ""  # first line of the docstring, when present
    depth: int = 0  # nesting level, for indentation


@dataclass
class SkeletonFile:
    """One file stripped to its structure."""

    path: str
    language: str
    entries: list[SkeletonEntry] = field(default_factory=list)
    parsed: bool = True
    error: str | None = None  # why parsing failed (syntax, missing extra)


@dataclass
class BonesResult:
    """Implementation stripped, structure kept: the compact code map."""

    provenance: Provenance
    files: list[SkeletonFile] = field(default_factory=list)
    parsed_files: int = 0
    skipped_files: int = 0


@dataclass
class ScryDelta:
    """One file's churn between the two refs."""

    path: str
    commits: int = 0
    insertions: int = 0
    deletions: int = 0


@dataclass
class ScryResult:
    """What changed between two refs: churn, files, and contributors."""

    provenance: Provenance
    ref_a: str = ""
    ref_b: str = ""
    commits: int = 0
    insertions: int = 0
    deletions: int = 0
    files: list[ScryDelta] = field(default_factory=list)
    souls: list[AuthorShare] = field(default_factory=list)  # active in the range
    new_souls: list[str] = field(default_factory=list)  # first seen inside the range


@dataclass
class Dependency:
    """One dependency read from a manifest."""

    name: str
    version: str | None
    ecosystem: str  # "PyPI" or "npm"
    manifest: str
    pinned: bool = False


@dataclass
class Affliction:
    """One known vulnerability afflicting a pinned dependency."""

    id: str
    package: str
    version: str
    ecosystem: str
    summary: str = ""


@dataclass
class PlagueResult:
    """Dependency manifests checked against the OSV database (opt-in network)."""

    provenance: Provenance
    dependencies: list[Dependency] = field(default_factory=list)
    afflictions: list[Affliction] = field(default_factory=list)
    checked: bool = False  # False when --offline (manifest parsing only)
    unpinned: int = 0  # dependencies skipped because no exact version


@dataclass
class GraveOutcome:
    """One repo's fate in a necropolis fan-out."""

    name: str
    source: str
    ok: bool = False
    exit_code: int = 0
    artifact: str = ""
    error: str = ""


@dataclass
class NecropolisResult:
    """A command fanned across every grave in the manifest."""

    command: str
    graves: list[GraveOutcome] = field(default_factory=list)
    index: str = ""  # path of the combined index artifact


@dataclass
class CacheEntry:
    """One interred repo in the catacombs."""

    path: str
    url: str
    size_bytes: int
    last_used: float


@dataclass
class BanishResult:
    """What the exorcism removed."""

    removed: list[CacheEntry] = field(default_factory=list)
    kept: list[CacheEntry] = field(default_factory=list)
    reclaimed_bytes: int = 0
