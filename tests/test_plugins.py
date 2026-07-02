"""Third-party rituals: the entry-point loader."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import typer

from git_reaper import plugins


@dataclass
class FakeEntryPoint:
    name: str
    target: Any

    def load(self) -> Any:
        if isinstance(self.target, Exception):
            raise self.target
        return self.target


def _sub_app() -> typer.Typer:
    sub = typer.Typer(name="ouija")

    @sub.command("ask")
    def ask() -> None:  # pragma: no cover - registration is what matters
        pass

    return sub


def _patch(monkeypatch, *eps: FakeEntryPoint) -> None:
    monkeypatch.setattr(plugins, "entry_points", lambda group: list(eps))


def test_a_typer_app_is_mounted(monkeypatch):
    _patch(monkeypatch, FakeEntryPoint("ouija", _sub_app()))
    app = typer.Typer()
    (fate,) = plugins.attach(app)
    assert fate.ok
    assert [g.name for g in app.registered_groups] == ["ouija"]


def test_a_factory_callable_is_invoked(monkeypatch):
    _patch(monkeypatch, FakeEntryPoint("ouija", _sub_app))
    app = typer.Typer()
    (fate,) = plugins.attach(app)
    assert fate.ok and [g.name for g in app.registered_groups] == ["ouija"]


def test_a_broken_ritual_is_reported_not_fatal(monkeypatch):
    _patch(
        monkeypatch,
        FakeEntryPoint("cursed", ImportError("dead import")),
        FakeEntryPoint("ouija", _sub_app()),
    )
    app = typer.Typer()
    fates = plugins.attach(app)
    assert [(f.name, f.ok) for f in fates] == [("cursed", False), ("ouija", True)]
    assert "dead import" in fates[0].error
    assert [g.name for g in app.registered_groups] == ["ouija"]


def test_a_non_typer_object_is_refused(monkeypatch):
    _patch(monkeypatch, FakeEntryPoint("junk", object()))
    app = typer.Typer()
    (fate,) = plugins.attach(app)
    assert not fate.ok and "typer.Typer" in fate.error
    assert app.registered_groups == []
