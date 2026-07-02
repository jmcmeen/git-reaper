"""OSV advisory lookups for `plague`. The only network code in the reaper,
opt-in by design: `--offline` never imports the transport at all.

Queries go to the batch endpoint (one POST for the whole manifest), then
each hit is fleshed out with its summary via the per-vuln endpoint.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_VULN_URL = "https://api.osv.dev/v1/vulns/{id}"

_TIMEOUT = 30


class OsvError(RuntimeError):
    """The oracle did not answer. Message carries the plain cause."""


def _post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "git-reaper"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            data: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            return data
    except Exception as exc:
        raise OsvError(f"OSV query failed: {exc}") from exc


def _get(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "git-reaper"})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            data: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            return data
    except Exception as exc:
        raise OsvError(f"OSV lookup failed: {exc}") from exc


def query_batch(queries: list[dict[str, Any]]) -> list[list[str]]:
    """Vulnerability ids per query, aligned with the input order."""
    if not queries:
        return []
    data = _post(OSV_BATCH_URL, {"queries": queries})
    results = data.get("results", [])
    ids: list[list[str]] = []
    for entry in results:
        vulns = entry.get("vulns") or []
        ids.append([v["id"] for v in vulns if "id" in v])
    return ids


def vuln_summary(vuln_id: str) -> str:
    """One line about a vulnerability, for the report."""
    data = _get(OSV_VULN_URL.format(id=vuln_id))
    summary = data.get("summary") or data.get("details") or ""
    return str(summary).strip().splitlines()[0] if summary else ""
