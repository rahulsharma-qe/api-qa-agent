"""The Docker image stays whole: everything the install needs is let into the build and copied in.
(The image itself is built and run in CI; this catches a new package or file left out of it.)"""

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _needed_by_the_install() -> set[str]:
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    packages = {name.rstrip("*") for name in project["tool"]["setuptools"]["packages"]["find"]["include"]}
    return packages | {"pyproject.toml", project["project"]["readme"], *project["project"]["license-files"]}


def test_every_package_and_file_the_install_needs_is_let_into_the_build():
    let_in = {line[1:] for line in (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()
              if line.startswith("!")}
    assert _needed_by_the_install() <= let_in


def test_every_package_and_file_the_install_needs_is_copied_into_the_image():
    copied = set()
    for sources in re.findall(r"^COPY (.+) \S+$", (REPO / "Dockerfile").read_text(encoding="utf-8"), re.M):
        copied |= set(sources.split())
    assert _needed_by_the_install() <= copied


def test_the_image_runs_qa_agent_in_the_mounted_project_folder():
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    assert 'ENTRYPOINT ["qa-agent"]' in dockerfile
    assert "\nWORKDIR /project\n" in dockerfile
