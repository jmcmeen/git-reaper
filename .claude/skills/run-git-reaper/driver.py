"""Headless driver for the `reaper summon` TUI.

Runs ReaperApp under Textual's test harness (no terminal, no tmux, no X)
and executes simple commands piped on stdin. One command per line:

    ss <path.svg>         save an SVG screenshot of the current screen
    press <k1> <k2> ...   send key presses (textual key names: down, enter, r, q ...)
    click <selector>      click a widget, e.g. click #reap
    type <text>           type literal text into the focused widget
    text <selector>       print a widget's renderable text to stdout
    eval <python-expr>    eval an expression; `app` and `pilot` are in scope
    wait <seconds>        let timers/workers run (reaps happen in a worker)
    quit                  exit the app cleanly (EOF also quits)

Usage (from the repo root):

    uv run python .claude/skills/run-git-reaper/driver.py [source] <<'EOF'
    ss /tmp/summon.svg
    press down down enter
    press r
    wait 3
    ss /tmp/reaped.svg
    quit
    EOF

Output lines are prefixed `[driver]`; `text`/`eval` results print raw.
"""

from __future__ import annotations

import asyncio
import shlex
import sys

from git_reaper.tui import ReaperApp

SIZE = (140, 40)


def say(msg: str) -> None:
    print(f"[driver] {msg}", flush=True)


async def main() -> None:
    source = sys.argv[1] if len(sys.argv) > 1 else "."
    app = ReaperApp(source)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        say(f"launched source={source!r} size={SIZE}")
        for raw in sys.stdin:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            cmd, _, tail = line.partition(" ")
            tail = tail.strip()
            rest = shlex.split(tail)
            try:
                if cmd == "quit":
                    break
                elif cmd == "ss":
                    path = rest[0]
                    app.save_screenshot(path)
                    say(f"screenshot -> {path}")
                elif cmd == "press":
                    await pilot.press(*rest)
                    await pilot.pause()
                    say(f"pressed {rest}")
                elif cmd == "click":
                    await pilot.click(rest[0])
                    await pilot.pause()
                    say(f"clicked {rest[0]}")
                elif cmd == "type":
                    await pilot.press(*list(tail))
                    await pilot.pause()
                elif cmd == "text":
                    # search the *topmost* screen so modals (SaveScreen etc.) resolve
                    widget = app.screen.query_one(tail)
                    content = None
                    for attr in ("value", "text"):  # Input.value, TextArea.text
                        got = getattr(widget, attr, None)
                        if isinstance(got, str):
                            content = got
                            break
                    if content is None:  # Static/Label: render() yields the content
                        content = str(widget.render())
                    print(content, flush=True)
                elif cmd == "eval":
                    result = eval(tail, {"app": app, "pilot": pilot})  # tail is raw, unquoted
                    print(repr(result), flush=True)
                elif cmd == "wait":
                    await asyncio.sleep(float(rest[0]))
                    await pilot.pause()
                    say(f"waited {rest[0]}s")
                else:
                    say(f"unknown command: {cmd}")
            except Exception as exc:  # keep the REPL alive on bad commands
                say(f"ERROR {cmd}: {exc!r}")
        say("exiting")


if __name__ == "__main__":
    asyncio.run(main())
