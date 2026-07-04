"""Leech: fenced blocks drained back into files, safely."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from git_reaper.cli import app
from git_reaper.core import leech as leech_core
from git_reaper.models import RepoRef

runner = CliRunner()

REPO = RepoRef(source="doc.md", kind="local", path=".")

DOC = """# a tutorial

```python
print("one")
```

```python title=app.py
print("two")
```

```src/setup.sh
echo three
```

~~~json
{"four": true}
~~~
"""


def _leech(text: str, lang: str | None = None):
    return leech_core.leech(text, "doc.md", REPO, lang=lang)


def test_leech_drains_named_and_numbered_blocks():
    result, contents = _leech(DOC)
    assert [b.path for b in result.blocks] == [
        "doc.block-01.py",
        "app.py",
        "src/setup.sh",
        "doc.block-04.json",
    ]
    assert contents["app.py"] == 'print("two")\n'
    assert contents["src/setup.sh"] == "echo three\n"
    named = {b.path: b.named for b in result.blocks}
    assert named["app.py"] and named["src/setup.sh"]
    assert not named["doc.block-01.py"]


def test_leech_language_filter():
    result, contents = _leech(DOC, lang="python")
    assert set(contents) == {"doc.block-01.py", "app.py"}
    assert result.skipped == 2


def test_leech_ignores_inner_fences():
    doc = "````md\n```python\nnested\n```\n````\n"
    result, contents = _leech(doc)
    assert len(result.blocks) == 1
    assert "```python" in next(iter(contents.values()))


def test_leech_refuses_traversal():
    with pytest.raises(leech_core.LeechError):
        _leech("```python title=../evil.py\nboo\n```\n")


def test_leech_dedupes_same_name():
    doc = "```python title=x.py\na\n```\n\n```python title=x.py\nb\n```\n"
    _result, contents = _leech(doc)
    assert set(contents) == {"x.py", "x-2.py"}
    assert contents["x.py"] == "a\n" and contents["x-2.py"] == "b\n"


def test_leech_unterminated_fence_is_prose():
    result, contents = _leech("```python\nnever closed\n")
    assert result.blocks == [] and contents == {}


def test_write_blocks_wants_an_empty_plot(tmp_path):
    out = tmp_path / "risen"
    out.mkdir()
    (out / "squatter.txt").write_text("here first\n", encoding="utf-8")
    with pytest.raises(Exception, match="not empty"):
        leech_core.write_blocks({"a.py": "x\n"}, out)
    leech_core.write_blocks({"a.py": "x\n"}, out, force=True)
    assert (out / "a.py").read_text(encoding="utf-8") == "x\n"


def test_write_blocks_archives_and_returns_the_archive_path(tmp_path):
    out = tmp_path / "risen"
    written = leech_core.write_blocks({"a.py": "x\n"}, out, archive="tar")
    assert not out.exists()
    assert written == out.with_name("risen.tar")
    assert written.is_file()


def test_leech_cli_zip_format(tmp_path):
    doc = tmp_path / "guide.md"
    doc.write_text(DOC, encoding="utf-8")
    out = tmp_path / "drained"
    result = runner.invoke(
        app, ["--plain", "leech", str(doc), "--out", str(out), "--format", "zip"]
    )
    assert result.exit_code == 0, result.output
    assert not out.exists()
    assert (tmp_path / "drained.zip").is_file()


def test_leech_cli_round_trip(tmp_path, monkeypatch):
    doc = tmp_path / "guide.md"
    doc.write_text(DOC, encoding="utf-8")
    out = tmp_path / "drained"
    result = runner.invoke(app, ["--plain", "leech", str(doc), "--out", str(out)])
    assert result.exit_code == 0
    assert "schema:    leech/v1" in result.stdout
    assert (out / "app.py").read_text(encoding="utf-8") == 'print("two")\n'
    assert (out / "src" / "setup.sh").is_file()

    missing = runner.invoke(app, ["--plain", "leech"])
    assert missing.exit_code == 1
