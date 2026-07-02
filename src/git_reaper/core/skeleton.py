"""Bones: strip implementation, keep structure.

Emits every file's imports, class/function signatures, and docstring first
lines - a compact code map that fits huge repos into small contexts.

Python parses with the stdlib `ast` (zero deps, exact). Other languages go
through tree-sitter when the `git-reaper[bones]` extra is installed; without
it they are reported as skipped, never silently dropped.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from git_reaper import fsutil
from git_reaper.core.provenance import make_provenance
from git_reaper.ignore import IgnoreMatcher, walk_files
from git_reaper.models import BonesResult, RepoRef, SkeletonEntry, SkeletonFile
from git_reaper.schemas import artifact_schema

#: Languages tree-sitter can strip, keyed by extension. Python is handled
#: natively and never needs the extra.
TS_LANGUAGES: dict[str, str] = {
    ".c": "c",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".h": "c",
    ".hpp": "cpp",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".php": "php",
    ".rb": "ruby",
    ".rs": "rust",
    ".ts": "typescript",
    ".tsx": "tsx",
}

#: tree-sitter node types that count as bones, mapped to our entry kind.
_TS_KINDS: dict[str, str] = {
    "function_declaration": "function",
    "function_definition": "function",
    "function_item": "function",
    "method_definition": "method",
    "method_declaration": "method",
    "class_declaration": "class",
    "class_definition": "class",
    "class_specifier": "class",
    "struct_item": "class",
    "enum_item": "class",
    "trait_item": "class",
    "impl_item": "class",
    "interface_declaration": "class",
    "module": "class",  # ruby modules
}


def bones(
    repo: RepoRef,
    excludes: list[str] | None = None,
    invoked: str = "reaper bones",
    generated: str | None = None,
) -> BonesResult:
    """Walk the tree and reduce every recognized source file to its bones."""
    root = Path(repo.path)
    matcher = IgnoreMatcher(root, extra_excludes=excludes)
    result = BonesResult(
        provenance=make_provenance(artifact_schema("bones"), repo, invoked, generated)
    )

    for path in walk_files(root, matcher):
        ext = path.suffix.lower()
        if ext != ".py" and ext not in TS_LANGUAGES:
            continue
        if fsutil.is_binary(path):
            continue
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        if ext == ".py":
            file = _python_bones(rel, text)
        else:
            file = _treesitter_bones(rel, TS_LANGUAGES[ext], text)
        result.files.append(file)
        if file.parsed:
            result.parsed_files += 1
        else:
            result.skipped_files += 1

    result.provenance.files = result.parsed_files
    return result


# --------------------------------------------------------------------------
# python, via ast
# --------------------------------------------------------------------------


def _python_bones(rel: str, text: str) -> SkeletonFile:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return SkeletonFile(
            path=rel,
            language="python",
            parsed=False,
            error=f"syntax error: {exc.msg} (line {exc.lineno})",
        )
    file = SkeletonFile(path=rel, language="python")
    _walk_python(tree.body, file.entries, depth=0)
    return file


def _first_doc_line(node: ast.AST) -> str:
    doc = (
        ast.get_docstring(node, clean=True)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        else None
    )
    return doc.strip().splitlines()[0] if doc else ""


def _walk_python(body: list[ast.stmt], entries: list[SkeletonEntry], depth: int) -> None:
    for node in body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            entries.append(
                SkeletonEntry(
                    kind="import",
                    name=_import_name(node),
                    signature=ast.unparse(node),
                    line=node.lineno,
                    depth=depth,
                )
            )
        elif isinstance(node, ast.ClassDef):
            entries.append(
                SkeletonEntry(
                    kind="class",
                    name=node.name,
                    signature=_class_signature(node),
                    line=node.lineno,
                    doc=_first_doc_line(node),
                    depth=depth,
                )
            )
            _walk_python(node.body, entries, depth + 1)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            entries.append(
                SkeletonEntry(
                    kind="method" if depth else "function",
                    name=node.name,
                    signature=_function_signature(node),
                    line=node.lineno,
                    doc=_first_doc_line(node),
                    depth=depth,
                )
            )


def _import_name(node: ast.Import | ast.ImportFrom) -> str:
    if isinstance(node, ast.ImportFrom):
        return node.module or "."
    return node.names[0].name


def _class_signature(node: ast.ClassDef) -> str:
    heads = [ast.unparse(base) for base in node.bases]
    heads += [f"{kw.arg}={ast.unparse(kw.value)}" for kw in node.keywords if kw.arg]
    inherit = f"({', '.join(heads)})" if heads else ""
    return f"class {node.name}{inherit}"


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({ast.unparse(node.args)}){returns}"


# --------------------------------------------------------------------------
# everything else, via the optional tree-sitter extra
# --------------------------------------------------------------------------


def _get_parser(language: str) -> Any | None:
    try:
        import tree_sitter_language_pack
    except ImportError:
        return None
    try:
        return tree_sitter_language_pack.get_parser(language)
    except Exception:
        return None


def _treesitter_bones(rel: str, language: str, text: str) -> SkeletonFile:
    parser = _get_parser(language)
    if parser is None:
        return SkeletonFile(
            path=rel,
            language=language,
            parsed=False,
            error=f"no parser for {language}; install `git-reaper[bones]`",
        )
    raw = text.encode("utf-8")
    file = SkeletonFile(path=rel, language=language)
    try:
        tree = _parse(parser, raw, text)
        root = tree.root_node() if callable(tree.root_node) else tree.root_node
        _walk_treesitter(root, raw, file.entries, depth=0)
    except Exception as exc:  # a wobbly binding must not crash the whole map
        file.parsed = False
        file.error = f"tree-sitter parse failed: {exc}"
        file.entries.clear()
    return file


def _parse(parser: Any, raw: bytes, text: str) -> Any:
    """Bindings disagree on whether parse() wants bytes or str; try both."""
    try:
        return parser.parse(raw)
    except TypeError:
        return parser.parse(text)


# tree-sitter Python bindings disagree on the Node surface (property vs method,
# `type` vs `kind`, `children` vs `child(i)`). These normalizers paper over it.


def _resolve(value: Any) -> Any:
    return value() if callable(value) else value


def _node_type(node: Any) -> str:
    kind = getattr(node, "type", None)
    if kind is None:
        kind = getattr(node, "kind", None)
    return str(_resolve(kind))


def _node_children(node: Any) -> list[Any]:
    children = getattr(node, "children", None)
    if children is not None:
        resolved = _resolve(children)
        if resolved is not None:
            return list(resolved)
    count = _resolve(getattr(node, "child_count", 0))
    return [node.child(i) for i in range(int(count))]


def _node_line(node: Any) -> int:
    point = _resolve(getattr(node, "start_point", None) or getattr(node, "start_position", None))
    row = point.row if hasattr(point, "row") else point[0]
    return int(row) + 1


def _walk_treesitter(node: Any, raw: bytes, entries: list[SkeletonEntry], depth: int) -> None:
    for child in _node_children(node):
        kind = _TS_KINDS.get(_node_type(child))
        if kind is None:
            _walk_treesitter(child, raw, entries, depth)
            continue
        if kind == "function" and depth:
            kind = "method"
        entries.append(
            SkeletonEntry(
                kind=kind,
                name=_ts_name(child, raw),
                signature=_ts_signature(child, raw),
                line=_node_line(child),
                depth=depth,
            )
        )
        _walk_treesitter(child, raw, entries, depth + 1)


def _byte_span(node: Any) -> tuple[int, int]:
    return int(_resolve(node.start_byte)), int(_resolve(node.end_byte))


def _ts_name(node: Any, raw: bytes) -> str:
    named = node.child_by_field_name("name")
    if named is None:
        return ""
    start, end = _byte_span(named)
    return raw[start:end].decode("utf-8", errors="replace")


def _ts_signature(node: Any, raw: bytes) -> str:
    """The declaration's first line, trimmed at its body brace."""
    start, end = _byte_span(node)
    text = raw[start:end].decode("utf-8", errors="replace")
    head = text.split("{", 1)[0].split("\n", 1)[0].strip()
    return head.rstrip(" {;")
