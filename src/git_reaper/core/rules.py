"""The shared secret/PII rules engine behind exhume and veil.

One engine, two rituals: `exhume` detects (full history, masked previews),
`veil` redacts (any artifact, `[VEILED:rule-name]`). Neither ever writes a
full secret to any output, log, or error message - a found secret appears
only as `AKIA...9X2Q (masked)`.

Built-in signatures cover the common key formats plus a Shannon-entropy
sweep for the ones that have no format. The grimoire extends the set:

    [rules.internal-hostname]
    pattern = "[a-z0-9-]+\\.corp\\.example\\.com"
    severity = "medium"
    veil_only = true   # redacted by veil, never reported by exhume
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from git_reaper.core.provenance import make_provenance
from git_reaper.gitio import GitBackend, GitError, default_backend
from git_reaper.models import (
    ExhumeResult,
    RepoRef,
    SecretFinding,
    VeilCount,
    VeilResult,
)
from git_reaper.schemas import artifact_schema

SEVERITIES = ("low", "medium", "high")

#: Blobs larger than this are skipped; secrets live in text, not tarballs.
MAX_SCAN_BYTES = 1_000_000

ENTROPY_RULE = "high-entropy-string"
_ENTROPY_THRESHOLD = 4.5
_ENTROPY_CANDIDATE = re.compile(r"[A-Za-z0-9+/=_\-]{32,}")

#: Lock and generated dependency files are full of legitimate high-entropy
#: hashes (wheel digests, integrity fields). The entropy sweep skips them by
#: name to avoid crying wolf; the signature rules still run on them, so a
#: genuine key committed to a lock file is still caught.
_ENTROPY_SKIP_NAMES = frozenset(
    {
        "uv.lock",
        "poetry.lock",
        "Pipfile.lock",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "Cargo.lock",
        "composer.lock",
        "Gemfile.lock",
        "go.sum",
        "flake.lock",
    }
)


def _entropy_wanted(path: str, with_entropy: bool) -> bool:
    return with_entropy and path.rsplit("/", 1)[-1] not in _ENTROPY_SKIP_NAMES


@dataclass(frozen=True)
class Rule:
    """One signature: a name, a compiled pattern, and how loudly to scream."""

    name: str
    pattern: re.Pattern[str]
    severity: str = "high"
    veil_only: bool = False  # PII-ish rules veil redacts but exhume ignores


@dataclass
class RuleMatch:
    """One raw hit inside a text: which rule, where, and the matched span."""

    rule: Rule
    secret: str
    line: int


def _rule(name: str, pattern: str, severity: str = "high", veil_only: bool = False) -> Rule:
    return Rule(name=name, pattern=re.compile(pattern), severity=severity, veil_only=veil_only)


#: The built-in gallery. Order matters: the first rule to claim a span wins,
#: so specific signatures sit above the generic ones.
BUILTIN_RULES: tuple[Rule, ...] = (
    _rule("aws-access-key", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    _rule("github-token", r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b"),
    _rule("github-pat", r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
    _rule("gitlab-token", r"\bglpat-[A-Za-z0-9_\-]{20,}\b"),
    _rule("slack-token", r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),
    _rule("stripe-key", r"\b[sr]k_live_[A-Za-z0-9]{20,}\b"),
    _rule("google-api-key", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    _rule("anthropic-key", r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"),
    _rule("openai-key", r"\bsk-(?:proj-)?[A-Za-z0-9]{40,}\b"),
    _rule(
        "private-key",
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-----",
    ),
    _rule(
        "jwt",
        r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}\b",
        severity="medium",
    ),
    _rule(
        "password-assignment",
        r"(?i)\b(?:password|passwd|secret)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]",
        severity="medium",
    ),
    # PII the veil hides but the exhumation does not report as a secret.
    _rule("email", r"\b[\w.+-]+@[\w-]+\.[\w.-]+[\w]\b", severity="low", veil_only=True),
    _rule("ipv4", r"\b(?:\d{1,3}\.){3}\d{1,3}\b", severity="low", veil_only=True),
)


class RuleError(ValueError):
    """A custom rule is miswritten. Message names the rule and the sin."""


def load_rules(custom: dict[str, dict[str, object]] | None = None) -> list[Rule]:
    """The built-ins plus grimoire extensions (see config.custom_rules)."""
    rules = list(BUILTIN_RULES)
    for name, spec in (custom or {}).items():
        pattern = spec.get("pattern")
        if not isinstance(pattern, str):
            raise RuleError(f"rule {name!r} needs a string 'pattern'")
        severity = str(spec.get("severity", "medium"))
        if severity not in SEVERITIES:
            raise RuleError(f"rule {name!r}: severity must be one of {', '.join(SEVERITIES)}")
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise RuleError(f"rule {name!r}: bad pattern: {exc}") from exc
        rules.append(
            Rule(
                name=name,
                pattern=compiled,
                severity=severity,
                veil_only=bool(spec.get("veil_only", False)),
            )
        )
    return rules


def shannon_entropy(text: str) -> float:
    """Bits per character; random base64 sits near 6, English near 4."""
    if not text:
        return 0.0
    counts: dict[str, int] = {}
    for char in text:
        counts[char] = counts.get(char, 0) + 1
    total = len(text)
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


def mask(secret: str) -> str:
    """First/last 4 chars only, per the contract: never the full secret."""
    if len(secret) <= 8:
        return secret[:2] + "..."
    return f"{secret[:4]}...{secret[-4:]}"


def fingerprint(rule: str, secret: str) -> str:
    """Stable id for a finding that does not store the secret itself."""
    return hashlib.sha256(f"{rule}:{secret}".encode()).hexdigest()[:16]


def scan_text(
    text: str, rules: list[Rule] | None = None, with_entropy: bool = True
) -> list[RuleMatch]:
    """Every rule hit in a text, ordered by position. Overlaps: first rule wins."""
    rules = rules if rules is not None else list(BUILTIN_RULES)
    claimed: list[tuple[int, int]] = []
    matches: list[tuple[int, RuleMatch]] = []

    def _claim(start: int, end: int) -> bool:
        for s, e in claimed:
            if start < e and end > s:
                return False
        claimed.append((start, end))
        return True

    for rule in rules:
        for m in rule.pattern.finditer(text):
            if _claim(m.start(), m.end()):
                line = text.count("\n", 0, m.start()) + 1
                matches.append((m.start(), RuleMatch(rule=rule, secret=m.group(0), line=line)))
    if with_entropy:
        entropy_rule = Rule(name=ENTROPY_RULE, pattern=_ENTROPY_CANDIDATE, severity="low")
        for m in _ENTROPY_CANDIDATE.finditer(text):
            if shannon_entropy(m.group(0)) < _ENTROPY_THRESHOLD:
                continue
            if _claim(m.start(), m.end()):
                line = text.count("\n", 0, m.start()) + 1
                hit = RuleMatch(rule=entropy_rule, secret=m.group(0), line=line)
                matches.append((m.start(), hit))
    matches.sort(key=lambda pair: pair[0])
    return [match for _pos, match in matches]


# --------------------------------------------------------------------------
# exhume: dig the secrets out of the full history
# --------------------------------------------------------------------------


def load_baseline(path: Path) -> set[str]:
    """Fingerprints to suppress: a JSON list of strings, or a previous
    `exhume --format json` report (fingerprints are pulled from findings)."""
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuleError(f"baseline {path} is unreadable: {exc}") from exc
    if isinstance(data, list):
        return {str(item) for item in data}
    if isinstance(data, dict):
        findings = data.get("findings", [])
        if isinstance(findings, list):
            return {
                str(f.get("fingerprint")) for f in findings if isinstance(f, dict)
            } - {"None"}
    raise RuleError(f"baseline {path}: expected a JSON list or an exhume JSON report")


def exhume(
    repo: RepoRef,
    rules: list[Rule] | None = None,
    with_entropy: bool = True,
    baseline: set[str] | None = None,
    invoked: str = "reaper exhume",
    generated: str | None = None,
    backend: GitBackend | None = None,
) -> ExhumeResult:
    """Scan every reachable blob in history for secrets.

    Each unique blob is read once; findings are attributed to the oldest
    commit that introduced the blob at its recorded path.
    """
    backend = backend or default_backend()
    root = Path(repo.path)
    if not backend.is_repo(root):
        raise GitError(f"not a git repository: {repo.source} (exhume digs through history)")
    rules = [r for r in (rules if rules is not None else list(BUILTIN_RULES)) if not r.veil_only]
    baseline = baseline or set()

    result = ExhumeResult(
        provenance=make_provenance(artifact_schema("exhume"), repo, invoked, generated)
    )
    for blob in backend.blobs(root):
        if blob.size_bytes > MAX_SCAN_BYTES:
            continue
        raw = backend.cat_blob(root, blob.sha)
        if raw is None or b"\0" in raw[:8192]:
            continue
        result.blobs_scanned += 1
        text = raw.decode("utf-8", errors="replace")
        matches = scan_text(
            text, rules=rules, with_entropy=_entropy_wanted(blob.path, with_entropy)
        )
        if not matches:
            continue
        attribution = backend.blob_commit(root, blob.sha, blob.path)
        sha, date, author = attribution or ("", "", "")
        for match in matches:
            print_ = fingerprint(match.rule.name, match.secret)
            if print_ in baseline:
                result.suppressed += 1
                continue
            result.findings.append(
                SecretFinding(
                    rule=match.rule.name,
                    severity=match.rule.severity,
                    path=blob.path,
                    line=match.line,
                    preview=mask(match.secret),
                    fingerprint=print_,
                    sha=sha,
                    date=date,
                    author=author,
                )
            )

    order = {"high": 0, "medium": 1, "low": 2}
    result.findings.sort(key=lambda f: (order.get(f.severity, 3), f.path, f.line, f.rule))
    result.provenance.files = len({f.path for f in result.findings})
    return result


def cursed(result: ExhumeResult, fail_on: str) -> bool:
    """CI gate: does this report warrant exit 3?"""
    if fail_on == "any":
        return bool(result.findings)
    if fail_on == "high":
        return any(f.severity == "high" for f in result.findings)
    raise RuleError(f"unknown --fail-on {fail_on!r} (use 'any' or 'high')")


# --------------------------------------------------------------------------
# veil: hide what the rules find
# --------------------------------------------------------------------------


@dataclass
class VeiledText:
    """A redacted text and the tally of what was hidden."""

    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def veil_text(
    text: str, rules: list[Rule] | None = None, with_entropy: bool = True
) -> VeiledText:
    """Replace every rule hit with `[VEILED:rule-name]`."""
    matches = scan_text(text, rules=rules, with_entropy=with_entropy)
    counts: dict[str, int] = {}
    pieces: list[str] = []
    cursor = 0
    offset_matches = _with_offsets(text, matches)
    for start, end, match in offset_matches:
        pieces.append(text[cursor:start])
        pieces.append(f"[VEILED:{match.rule.name}]")
        cursor = end
        counts[match.rule.name] = counts.get(match.rule.name, 0) + 1
    pieces.append(text[cursor:])
    return VeiledText(text="".join(pieces), counts=counts)


def _with_offsets(text: str, matches: list[RuleMatch]) -> list[tuple[int, int, RuleMatch]]:
    """Recover each match's span by searching forward from the last one.

    scan_text guarantees matches are position-ordered and non-overlapping,
    so a forward find on the exact secret text is unambiguous.
    """
    spans: list[tuple[int, int, RuleMatch]] = []
    cursor = 0
    for match in matches:
        start = text.find(match.secret, cursor)
        if start < 0:  # pragma: no cover - defensive; scan_text found it
            continue
        spans.append((start, start + len(match.secret), match))
        cursor = start + len(match.secret)
    return spans


def veil(
    text: str,
    source: str,
    repo: RepoRef,
    rules: list[Rule] | None = None,
    with_entropy: bool = True,
    invoked: str = "reaper veil",
    generated: str | None = None,
) -> tuple[VeilResult, str]:
    """Veil an artifact's text; returns (result, redacted text)."""
    veiled = veil_text(text, rules=rules, with_entropy=with_entropy)
    result = VeilResult(
        provenance=make_provenance(artifact_schema("veil"), repo, invoked, generated),
        input=source,
        replacements=[
            VeilCount(rule=name, count=count) for name, count in sorted(veiled.counts.items())
        ],
        total=veiled.total,
    )
    result.provenance.files = 1
    return result, veiled.text


def scrub(message: str, rules: list[Rule] | None = None) -> str:
    """Veil a log/debug line. --shriek output goes through this."""
    return veil_text(message, rules=rules).text
