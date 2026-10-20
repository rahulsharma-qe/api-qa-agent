"""import cases: into one file per feature, existing ids skipped unless --overwrite."""

from qa_agent.case_import import import_cases
from qa_agent.cases import load_case_file
from qa_agent.cli import main
from qa_agent.project import TeamProject

CSV = ("Case ID,Title,Criteria,Priority,Method,Path,Expected Status\n"
       "TC1,List,AC-1,P1,GET,/bookings,200\nTC2,Health,AC-1,P2,GET,/health-check,200\n")


def test_cases_go_to_a_file_named_after_the_feature_as_drafts(make_project):
    root = make_project({"existing/booking_api.csv": CSV})
    summary = import_cases(TeamProject.load(root), [root / "existing/booking_api.csv"])
    case_file = load_case_file(root / "cases/booking-api.yaml")
    assert [case.id for case in case_file.cases] == ["TC1", "TC2"]
    assert all(case.review.status == "draft" for case in case_file.cases)
    assert case_file.cases[0].source["file"] == "existing/booking_api.csv"
    assert summary.written == {"cases/booking-api.yaml": ["TC1", "TC2"]}


def test_an_id_already_in_the_project_is_skipped_unless_overwrite(make_project):
    root = make_project({"existing/booking_api.csv": CSV, "cases/old.yaml": """
        feature: Old
        cases:
          - {id: TC1, title: kept, steps_text: [x], review: {status: approved}}
        """})
    project = TeamProject.load(root)
    summary = import_cases(project, [root / "existing/booking_api.csv"])
    assert summary.skipped == ["TC1: already in cases/old.yaml (use --overwrite to replace it)"]
    assert load_case_file(root / "cases/old.yaml").cases[0].title == "kept"
    import_cases(project, [root / "existing/booking_api.csv"], overwrite=True)
    replaced = load_case_file(root / "cases/old.yaml").cases[0]
    assert (replaced.title, replaced.review.status) == ("List", "draft")


def test_into_puts_everything_in_one_file(make_project, capsys):
    root = make_project({"existing/booking_api.csv": CSV})
    assert main(["--project", str(root), "import", "cases", str(root / "existing/booking_api.csv"),
                 "--into", "cases/all.yaml"]) == 0
    assert [case.id for case in load_case_file(root / "cases/all.yaml").cases] == ["TC1", "TC2"]
    assert "2 cases imported as drafts, 0 skipped" in capsys.readouterr().out


def test_an_unknown_file_type_is_a_setup_problem(make_project, capsys):
    root = make_project({"existing/cases.txt": "x"})
    assert main(["--project", str(root), "import", "cases", str(root / "existing/cases.txt")]) == 2
    assert "use Excel (.xlsx), CSV" in capsys.readouterr().err


POSTMAN = ('{"info": {"name": "Smoke", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},'
           ' "item": [{"name": "Health", "request": {"method": "GET", "url": "{{baseUrl}}/health-check"}}]}')
FEATURE = """Feature: Refunds
  Scenario Outline: By time
    When I GET "/bookings/<pnr>/refund"
    Then the status is 200
    Examples:
      | pnr |
      | A1  |
"""


def test_a_case_without_an_id_gets_the_next_free_one_whatever_the_order(make_project):
    root = make_project({"existing/smoke.json": POSTMAN, "existing/refunds.feature": FEATURE,
                         "existing/booking_api.csv": CSV.replace("TC2,", "TC041,")},
                        config="team: t\nservice: bookings\nstacks: [python]\ncase_id_prefix: TC\n")
    project = TeamProject.load(root)
    summary = import_cases(project, [root / "existing/smoke.json", root / "existing/refunds.feature",
                                     root / "existing/booking_api.csv"])
    assert summary.new_ids == ["TC042: Health", "TC043: By time"]
    refunds = load_case_file(root / "cases/refunds.yaml").cases[0]
    assert refunds.data == "data/refunds-tc043.csv"
    assert (root / "data/refunds-tc043.csv").read_text().splitlines() == ["pnr", "A1"]


def test_importing_again_keeps_the_id_it_was_given(make_project):
    root = make_project({"existing/smoke.json": POSTMAN})
    project = TeamProject.load(root)
    import_cases(project, [root / "existing/smoke.json"])
    again = import_cases(project, [root / "existing/smoke.json"])
    assert again.new_ids == [] and again.skipped == ["TC001: already in cases/smoke.yaml (use --overwrite to replace it)"]
