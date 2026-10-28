"""qa-agent's version is written once in pyproject.toml and once in the package: they must agree, or
qa-agent --version (and the release tag the workflow checks against) would not tell the truth."""

import tomllib
from pathlib import Path

import qa_agent

REPO = Path(__file__).resolve().parents[2]


def test_the_package_and_pyproject_give_the_same_version():
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert qa_agent.__version__ == project["project"]["version"]


def test_the_docs_name_this_version_wherever_they_name_one():
    """The Docker tag and the workflow example people copy: a stale one points at an older release."""
    import re
    for name in ("docs/guide.md", "docs/getting-started.md", ".github/workflows/qa-agent-team.yml"):
        text = (REPO / name).read_text(encoding="utf-8")
        named = set(re.findall(r"qa-agent:(\d+\.\d+\.\d+)|qa-agent-team\.yml@v(\d+\.\d+\.\d+)|platform-ref: v(\d+\.\d+\.\d+)", text))
        assert {version for found in named for version in found if version} <= {qa_agent.__version__}, name
