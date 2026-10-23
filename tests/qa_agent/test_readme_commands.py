"""The README names every qa-agent command: a new command can't ship without it."""

import argparse
from pathlib import Path

from qa_agent.cli import _parser

REPO = Path(__file__).resolve().parents[2]


def _commands() -> list[str]:
    subcommands = next(action for action in _parser()._actions if isinstance(action, argparse._SubParsersAction))
    return list(subcommands.choices)


def test_the_readme_names_every_command():
    row = next(line for line in (REPO / "README.md").read_text(encoding="utf-8").splitlines()
               if line.startswith("| [`qa_agent/`]"))
    missing = [command for command in _commands() if f"`{command}`" not in row]
    assert _commands() and not missing, f"add to the qa_agent/ row of README.md: {', '.join(missing)}"
