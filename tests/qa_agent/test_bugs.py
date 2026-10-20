"""qa-agent bugs: the loop, the guards and the report, with the API and the tests stood in for.
(The real thing, with the reference API, runs in examples/bookings-team/run_all.sh and in CI.)"""

import pytest

from qa_agent import bugs
from qa_agent.cli import main
from qa_agent.project import SetupError, TeamProject

VARIANTS = """
start: python -m mock_service --bug {bug}
start_without_bugs: python -m mock_service
bugs:
  refund-boundary: a cancel at exactly 24 hours gets no refund
  token-not-checked: a call with no token is let through
"""


@pytest.fixture
def project(make_project):
    root = make_project({"bugs.yaml": VARIANTS, "config/dependencies.yaml": "attempts: 5\nchecks: []\n"})
    return TeamProject.load(root)


def stand_in(monkeypatch, already_up=False, failing=None):
    started = []

    def run_once(project, variants, stack, bug, folder):
        started.append(variants["start"].replace("{bug}", bug) if bug else variants["start_without_bugs"])
        return bugs._Outcome(1 if (failing or {}).get(bug) else 0, (failing or {}).get(bug, []))
    monkeypatch.setattr(bugs, "_run_once", run_once)
    monkeypatch.setattr(bugs, "_ready", lambda *args, **kwargs: already_up)
    return started


def test_a_clean_run_first_then_one_run_per_bug_and_the_rate(project, monkeypatch):
    started = stand_in(monkeypatch, failing={"refund-boundary": ["TC002", "TC040"]})
    report = bugs.measure(project, project.root / "bugs.yaml", "python")
    assert started == ["python -m mock_service", "python -m mock_service --bug refund-boundary",
                       "python -m mock_service --bug token-not-checked"]
    assert (report.caught, len(report.runs)) == (1, 2)
    text = report.as_text()
    assert "1 of 2 planted bugs caught (50%)" in text
    assert "caught  refund-boundary          by TC002, TC040" in text
    assert "missed  token-not-checked        a call with no token is let through: no test noticed" in text
    assert "| `token-not-checked` | a call with no token is let through | **no** | - |" in \
        (project.root / "reports/bug-detection.md").read_text()


def test_a_suite_that_fails_with_no_bug_is_not_measured(project, monkeypatch):
    stand_in(monkeypatch, failing={"": ["TC001"]})
    with pytest.raises(SetupError, match=r"fail with no bug switched on \(TC001\)"):
        bugs.measure(project, project.root / "bugs.yaml", "python")


def test_an_api_already_up_or_a_bad_variants_file_is_a_setup_problem(project, monkeypatch, capsys):
    stand_in(monkeypatch, already_up=True)
    assert main(["--project", str(project.root), "bugs", "--stack", "python"]) == 2
    assert "the API is already up" in capsys.readouterr().err
    (project.root / "bugs.yaml").write_text("start: python -m mock_service\nstart_without_bugs: x\nbugs: [x]\n")
    with pytest.raises(SetupError, match="a command with {bug} in it"):
        bugs.measure(project, project.root / "bugs.yaml", "python")
    with pytest.raises(SetupError, match="stack 'restassured' is not in qa-agent.yaml"):
        bugs.measure(project, project.root / "bugs.yaml", "restassured")
