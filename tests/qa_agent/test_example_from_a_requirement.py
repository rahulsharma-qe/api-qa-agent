"""The from-a-requirement example stays true: from its inputs alone (the requirement, the API, the
filled review sheets, the recorded replies), every step gives exactly what is committed."""

import filecmp
import io
import shutil
from pathlib import Path

from qa_agent.cli import main

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "from-a-requirement"
WRITTEN_BY_QA_AGENT = ["acceptance-criteria-drafts.yaml", "cases", "tests/generated"]


def run(project: Path, *args: str) -> int:
    return main(["--project", str(project), *args])


def test_every_step_from_the_inputs_gives_what_is_committed(tmp_path, monkeypatch, capsys):
    project = tmp_path / "team"
    shutil.copytree(EXAMPLE, project, ignore=shutil.ignore_patterns("__pycache__", "reports"))
    for name in WRITTEN_BY_QA_AGENT:
        target = project / name
        shutil.rmtree(target) if target.is_dir() else target.unlink()

    monkeypatch.setattr("sys.stdin", io.StringIO((project / "requirements/BOOK-101.md").read_text()))
    assert run(project, "draft", "criteria", "-", "--ref", "BOOK-101") == 1          # one criterion refused
    assert run(project, "review", "apply", "--sheet", "review/1-criteria.xlsx") == 0
    assert run(project, "draft", "cases") == 1                                        # one reply refused
    assert run(project, "review", "apply", "--sheet", "review/2-cases.xlsx") == 0
    assert run(project, "draft", "cases", "--redo", "TC005") == 0
    assert run(project, "draft", "cases", "--redo", "TC005") == 1                     # already redone
    assert run(project, "review", "apply", "--sheet", "review/3-redo.xlsx") == 0
    assert run(project, "generate") == 0
    capsys.readouterr()
    assert run(project, "ai-report") == 0                                            # every call, every decision
    report = capsys.readouterr().out
    assert "AI drafts       16: 13 approved, 3 rejected" in report and "Look at first   nothing" in report
    assert "no draft kept: the reply was refused by the checks, or held nothing new: draft POST /bookings/{pnr}/cancel" in report

    for name in WRITTEN_BY_QA_AGENT:
        built, committed = project / name, EXAMPLE / name
        if built.is_file():
            assert filecmp.cmp(built, committed, shallow=False), f"{name} differs from the committed one"
        else:
            compared = filecmp.dircmp(built, committed, ignore=["__pycache__"])
            assert not (compared.diff_files or compared.left_only or compared.right_only), f"{name} differs"


def test_every_recorded_reply_says_it_was_written_by_hand():
    replies = sorted((EXAMPLE / "ai/recorded").glob("*.txt"))
    assert replies
    for reply in replies:
        assert "# Hand-written reply: no model was called." in reply.read_text(), reply.name
