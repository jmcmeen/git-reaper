"""The conjure/reanimate round trip: reanimate(conjure(tree)) == tree,
byte for byte, including under adversarial contents."""

from __future__ import annotations

import string
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from git_reaper.core.pack import conjure, iter_parts
from git_reaper.core.source import resolve_source
from git_reaper.core.unpack import ReanimateError, reanimate

GENERATED = "2026-07-01T00:00:00Z"

#: Contents chosen to attack the format: fences, fake markers, no trailing
#: newline, CRLF, unicode line separators, emptiness.
NASTY = {
    "plain.md": "# hello\n",
    "no_newline.txt": "no trailing newline",
    "empty.txt": "",
    "fences.md": "````\nfour ticks inside\n````\nand ```three``` inline\n",
    "fake_marker.md": "<!-- end fake_marker.md -->\n<!-- end#1 fake_marker.md -->\nboo\n",
    "crlf.txt": "one\r\ntwo\r\n",
    "seps.txt": "a\u2028bc\n",  # unicode line separator
    "deep/nest/ed/file.py": "print('```')\n",
    "just_newline.txt": "\n",
}


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".git" not in p.parts
    }


def _pack_text(root: Path, **kwargs) -> str:
    repo = resolve_source(str(root)).repo
    result = conjure(repo, generated=GENERATED, **kwargs)
    return "".join(text for _, text in iter_parts(result))


def _write_tree_bytes(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))


def test_round_trip_nasty_contents(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_tree_bytes(src, NASTY)
    text = _pack_text(src, with_sha256=True)

    dst = tmp_path / "dst"
    result = reanimate(text, dst, verify=True)
    assert result.verify_failures == []
    assert result.schema == "conjure/v1"
    assert _tree_bytes(dst) == _tree_bytes(src)


def test_artifact_is_deterministic(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_tree_bytes(src, NASTY)
    assert _pack_text(src) == _pack_text(src)


def test_split_tokens_shards_and_round_trips(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    files = {f"f{i:02d}.txt": f"content number {i}\n" * 50 for i in range(6)}
    _write_tree_bytes(src, files)

    repo = resolve_source(str(src)).repo
    result = conjure(repo, split_tokens=300, generated=GENERATED)
    parts = list(iter_parts(result))
    assert result.parts == len(parts) > 1
    assert f"part:      1/{result.parts}" in parts[0][1]
    # only part 1 carries the tree
    assert "<!-- tree -->" in parts[0][1]
    assert "<!-- tree -->" not in parts[1][1]

    dst = tmp_path / "dst"
    reanimate("\n".join(text for _, text in parts), dst)
    assert _tree_bytes(dst) == _tree_bytes(src)


def test_verify_catches_corruption(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_tree_bytes(src, {"a.txt": "original words\n"})
    text = _pack_text(src, with_sha256=True)
    tampered = text.replace("original words", "corrupted words")

    result = reanimate(tampered, tmp_path / "dst", verify=True)
    assert result.verify_failures == ["a.txt"]


def test_skips_binaries_with_receipts(tmp_path, make_dir):
    root = make_dir({"keep.md": "x\n", "corpse.bin": b"\x00\x01\x02"})
    text = _pack_text(root)
    assert "<!-- skipped corpse.bin: binary -->" in text
    dst = tmp_path / "dst"
    result = reanimate(text, dst)
    assert [f.path for f in result.files] == ["keep.md"]


@pytest.mark.parametrize(
    "path",
    ["../evil.txt", "/etc/evil", "C:/evil", "a/../evil", "a\\evil", "a//b"],
)
def test_traversal_and_malformed_paths_refused(tmp_path, path):
    artifact = f"## {path}\n```\nboo\n```\n<!-- end {path} -->\n"
    with pytest.raises(ReanimateError, match="refusing"):
        reanimate(artifact, tmp_path / "dst")


def test_refuses_nonempty_out_without_force(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_tree_bytes(src, {"a.txt": "x\n"})
    text = _pack_text(src)
    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "squatter.txt").write_text("here first\n")
    with pytest.raises(ReanimateError, match="not empty"):
        reanimate(text, dst)
    reanimate(text, dst, force=True)
    assert (dst / "a.txt").read_text() == "x\n"


_NAME = st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=6)
_PATH = st.builds("/".join, st.lists(_NAME, min_size=1, max_size=3))
# \x00 would (correctly) trip binary detection; everything else is fair game
_CONTENT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    max_size=300,
)


def _no_dir_file_conflicts(tree: dict[str, str]) -> bool:
    return not any(q != p and q.startswith(p + "/") for p in tree for q in tree)


@settings(
    max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(tree=st.dictionaries(_PATH, _CONTENT, max_size=8).filter(_no_dir_file_conflicts))
def test_round_trip_property(tree: dict[str, str]):
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        src.mkdir()
        _write_tree_bytes(src, tree)
        text = _pack_text(src, with_sha256=True)
        dst = Path(tmp) / "dst"
        result = reanimate(text, dst, verify=True)
        assert result.verify_failures == []
        assert _tree_bytes(dst) == _tree_bytes(src)


def test_veiled_pack_hashes_verify_round_trip(tmp_path, make_dir):
    """--veil changes content, so hashes and receipts must describe the
    veiled bytes; reanimate --verify holds and the secret never lands."""
    from git_reaper.core.rules import BUILTIN_RULES

    secret = "AKIAABCDEFGHIJKLMNOP"
    root = make_dir({"config.py": f"KEY = '{secret}'\n", "safe.md": "# fine\n"})
    rules = list(BUILTIN_RULES)
    result = conjure(
        resolve_source(str(root)).repo, with_sha256=True, veil_rules=rules
    )
    assert result.veiled == 1
    text = "".join(part for _n, part in iter_parts(result, veil_rules=rules))
    assert secret not in text and "[VEILED:aws-access-key]" in text
    risen = tmp_path / "risen"
    outcome = reanimate(text, risen, verify=True)
    assert outcome.verify_failures == []
    assert "[VEILED:aws-access-key]" in (risen / "config.py").read_text()
