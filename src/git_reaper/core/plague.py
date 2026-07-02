"""Plague: check dependency manifests against the OSV database.

Manifest parsing is pure and offline. The network hop is injectable (and
lives in net/osv.py), so `--offline` degrades gracefully to manifest
parsing and tests never touch the wire.

Only exactly-pinned dependencies are queried - a range like `>=2.0` has no
single version to ask about - and every skip is counted, never silent.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from git_reaper.core.provenance import make_provenance
from git_reaper.models import Affliction, Dependency, PlagueResult, RepoRef
from git_reaper.schemas import artifact_schema

#: (queries) -> vuln id lists, aligned with input. The real one is
#: net.osv.query_batch; tests inject a fake.
BatchFn = Callable[[list[dict[str, Any]]], list[list[str]]]
SummaryFn = Callable[[str], str]

_PY_PIN = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*==\s*([\w.!+*-]+)")
_PY_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_NPM_EXACT = re.compile(r"^\d+\.\d+\.\d+(?:[-+][\w.]+)?$")


def plague(
    repo: RepoRef,
    offline: bool = False,
    query_batch: BatchFn | None = None,
    vuln_summary: SummaryFn | None = None,
    invoked: str = "reaper plague",
    generated: str | None = None,
) -> PlagueResult:
    """Read every manifest under the root; consult the oracle unless offline."""
    root = Path(repo.path)
    result = PlagueResult(
        provenance=make_provenance(artifact_schema("plague"), repo, invoked, generated)
    )
    result.dependencies = _read_manifests(root)
    result.unpinned = sum(1 for dep in result.dependencies if not dep.pinned)
    result.provenance.files = len({dep.manifest for dep in result.dependencies})
    if offline:
        return result

    if query_batch is None or vuln_summary is None:  # pragma: no cover - wired by the CLI
        from git_reaper.net import osv

        query_batch = query_batch or osv.query_batch
        vuln_summary = vuln_summary or osv.vuln_summary

    pinned = [dep for dep in result.dependencies if dep.pinned and dep.version]
    queries = [
        {"package": {"name": dep.name, "ecosystem": dep.ecosystem}, "version": dep.version}
        for dep in pinned
    ]
    for dep, ids in zip(pinned, query_batch(queries), strict=False):
        for vuln_id in ids:
            result.afflictions.append(
                Affliction(
                    id=vuln_id,
                    package=dep.name,
                    version=dep.version or "",
                    ecosystem=dep.ecosystem,
                    summary=vuln_summary(vuln_id),
                )
            )
    result.afflictions.sort(key=lambda a: (a.package, a.id))
    result.checked = True
    return result


def _read_manifests(root: Path) -> list[Dependency]:
    deps: list[Dependency] = []
    for manifest in sorted(root.glob("requirements*.txt")):
        deps.extend(_parse_requirements(manifest))
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        deps.extend(_parse_pyproject(pyproject))
    package_json = root / "package.json"
    if package_json.is_file():
        deps.extend(_parse_package_json(package_json))
    return deps


def _parse_requirements(path: Path) -> list[Dependency]:
    deps = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        deps.append(_python_dep(line, path.name))
    return deps


def _parse_pyproject(path: Path) -> list[Dependency]:
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError:
        return []
    project = data.get("project", {})
    specs: list[str] = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        specs.extend(group)
    for group in data.get("dependency-groups", {}).values():
        specs.extend(spec for spec in group if isinstance(spec, str))
    return [_python_dep(spec, path.name) for spec in specs if isinstance(spec, str)]


def _python_dep(spec: str, manifest: str) -> Dependency:
    spec = spec.split(";", 1)[0].strip()  # environment markers are not versions
    pin = _PY_PIN.match(spec)
    if pin and "*" not in pin.group(3):
        return Dependency(
            name=pin.group(1).lower(),
            version=pin.group(3),
            ecosystem="PyPI",
            manifest=manifest,
            pinned=True,
        )
    name = _PY_NAME.match(spec)
    return Dependency(
        name=(name.group(1).lower() if name else spec),
        version=None,
        ecosystem="PyPI",
        manifest=manifest,
        pinned=False,
    )


def _parse_package_json(path: Path) -> list[Dependency]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return []
    deps = []
    for section in ("dependencies", "devDependencies"):
        table = data.get(section, {})
        if not isinstance(table, dict):
            continue
        for name, version in sorted(table.items()):
            exact = isinstance(version, str) and bool(_NPM_EXACT.match(version))
            deps.append(
                Dependency(
                    name=name,
                    version=version if exact else None,
                    ecosystem="npm",
                    manifest=path.name,
                    pinned=exact,
                )
            )
    return deps
