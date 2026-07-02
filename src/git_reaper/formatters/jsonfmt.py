"""JSON rendering: dataclasses to stable, sorted, parseable JSON."""

from __future__ import annotations

import dataclasses
import json
from typing import Any


def to_jsonable(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(item) for item in obj]
    if isinstance(obj, dict):
        return {key: to_jsonable(value) for key, value in obj.items()}
    return obj


def render(obj: Any) -> str:
    """Deterministic JSON: stable key order, trailing newline, ASCII-safe."""
    return json.dumps(to_jsonable(obj), indent=2, ensure_ascii=True) + "\n"
