"""qa-agent's version is written once in pyproject.toml and once in the package: they must agree, or
qa-agent --version (and the release tag the workflow checks against) would not tell the truth."""

import tomllib
from pathlib import Path

import qa_agent

REPO = Path(__file__).resolve().parents[2]


def test_the_package_and_pyproject_give_the_same_version():
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert qa_agent.__version__ == project["project"]["version"]
