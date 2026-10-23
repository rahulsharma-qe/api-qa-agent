"""qa-agent bug-detection: the loop, the guards and the report, with the API and the tests stood in for.
(The real thing, with the reference API, runs in examples/bookings-team/run_all.sh and in CI.)"""

import pytest

from qa_agent import bug_detection
from qa_agent.cli import main
from qa_agent.project import SetupError, TeamProject

SEEDED_BUGS = """
start_with_bug: python -m demo_api --bug {bug}
start_clean: python -m demo_api
bugs:
  refund-boundary: a cancel at exactly 24 hours gets no refund
  token-not-checked: a call with no token is let through
"""


@pytest.fixture
def project(make_project):
    root = make_project({"seeded-bugs.yaml": SEEDED_BUGS, "config/dependencies.yaml": "attempts: 5\nchecks: []\n"})
    return TeamProject.load(root)


def stand_in(monkeypatch, already_up=False, failing=None):
    started = []

    def run_once(project, seeded, framework, bug, folder):
        started.append(seeded["start_with_bug"].replace("{bug}", bug) if bug else seeded["start_clean"])
        return bug_detection._Outcome(1 if (failing or {}).get(bug) else 0, (failing or {}).get(bug, []))
    monkeypatch.setattr(bug_detection, "_run_once", run_once)
    monkeypatch.setattr(bug_detection, "_ready", lambda *args, **kwargs: already_up)
    return started


def test_a_clean_run_first_then_one_run_per_bug_and_the_rate(project, monkeypatch):
    started = stand_in(monkeypatch, failing={"refund-boundary": ["TC002", "TC040"]})
    report = bug_detection.measure(project, project.root / "seeded-bugs.yaml", "pytest")
    assert started == ["python -m demo_api", "python -m demo_api --bug refund-boundary",
                       "python -m demo_api --bug token-not-checked"]
    assert (report.caught, len(report.runs)) == (1, 2)
    text = report.as_text()
    assert "1 of 2 seeded bugs caught (50%)" in text
    assert "caught  refund-boundary          by TC002, TC040" in text
    assert "missed  token-not-checked        a call with no token is let through: no test noticed" in text
    assert "| `token-not-checked` | a call with no token is let through | **no** | - |" in \
        (project.root / "reports/bug-detection.md").read_text()


def test_a_suite_that_fails_with_no_bug_is_not_measured(project, monkeypatch):
    stand_in(monkeypatch, failing={"": ["TC001"]})
    with pytest.raises(SetupError, match=r"fail with no bug switched on \(TC001\)"):
        bug_detection.measure(project, project.root / "seeded-bugs.yaml", "pytest")


def test_an_api_already_up_or_a_bad_seeded_bugs_file_is_a_setup_problem(project, monkeypatch, capsys):
    stand_in(monkeypatch, already_up=True)
    assert main(["--project", str(project.root), "bug-detection", "--framework", "pytest"]) == 2
    assert "the API is already up" in capsys.readouterr().err
    (project.root / "seeded-bugs.yaml").write_text("start_with_bug: python -m demo_api\nstart_clean: x\nbugs: [x]\n")
    with pytest.raises(SetupError, match="a command with {bug} in it"):
        bug_detection.measure(project, project.root / "seeded-bugs.yaml", "pytest")
    with pytest.raises(SetupError, match="framework 'restassured' is not in qa-agent.yaml"):
        bug_detection.measure(project, project.root / "seeded-bugs.yaml", "restassured")
