"""check warns on cases with different ids and the same steps: once per group on the console, per case
for the review sheet; fast on a big regression pack."""

import time

import yaml

from qa_agent.checks import WARNING, check_project
from qa_agent.project import TeamProject

from tests.qa_agent.conftest import API

SEARCH = "[{request: {method: GET, path: /bookings/search}, expect: {status: 200}}]"


def project_with(make_project, files):
    return TeamProject.load(make_project({"api/api.yaml": API, **files}))


def duplicates(report):
    return [(f.case_id, f.message) for f in report.findings if f.level == WARNING and f.same_as]


def test_the_same_steps_under_other_ids_are_named_against_the_lowest_id(make_project):
    project = project_with(make_project, {
        "cases/a.yaml": f"feature: A\ncases:\n  - {{id: TC10, title: Search, steps: {SEARCH}}}\n"
                        f"  - {{id: TC2, title: Find bookings, priority: P0, steps: {SEARCH}}}\n",
        "cases/b.yaml": f"feature: B\ncases:\n  - {{id: TC31, title: Search again, tags: [smoke], steps: {SEARCH}}}\n"})
    report = check_project(project)
    assert duplicates(report) == [
        ("TC10", "TC10: same steps as TC2 (cases/a.yaml). Fix: reject one in the review sheet, or remove it"),
        ("TC31", "TC31: same steps as TC2 (cases/a.yaml). Fix: reject one in the review sheet, or remove it")]
    text = report.as_text()
    assert "warning  TC10, TC31: same steps as TC2 (cases/a.yaml)" in text and text.count("same steps as TC2") == 1
    assert "1 group of duplicate cases (2 cases repeating another case's steps)" in text


def test_other_values_a_rejected_case_and_manual_steps(make_project):
    other_pnr = "[{request: {method: GET, path: /bookings/AB12CD}, expect: {status: 200}}]"
    same_pnr = "[{request: {method: GET, path: /bookings/AB12CD}, expect: {status: 404}}]"
    project = project_with(make_project, {"cases/a.yaml": f"""
feature: A
cases:
  - {{id: TC1, title: a, steps: {other_pnr}}}
  - {{id: TC2, title: b, steps: {same_pnr}}}
  - {{id: TC3, title: c, steps: {other_pnr}, review: {{status: rejected}}}}
  - {{id: TC4, title: d, manual_steps: [Make a booking., Cancel it.]}}
  - {{id: TC5, title: e, manual_steps: ["make a  booking.", "Cancel it."]}}
"""})
    assert [case_id for case_id, _ in duplicates(check_project(project))] == ["TC5"]       # TC1/TC2 differ; TC3 rejected


def test_a_duplicate_shows_in_the_review_sheet_row_of_each_repeat(make_project):
    project = project_with(make_project, {
        "cases/a.yaml": f"feature: A\ncases:\n  - {{id: TC1, title: a, steps: {SEARCH}}}\n  - {{id: TC2, title: b, steps: {SEARCH}}}\n"})
    report = check_project(project)
    assert [f.message for f in report.for_case("TC2") if f.same_as] == [
        "TC2: same steps as TC1 (cases/a.yaml). Fix: reject one in the review sheet, or remove it"]
    assert not [f for f in report.for_case("TC1") if f.same_as]


def test_a_pack_of_five_thousand_cases_is_compared_in_well_under_a_second(make_project):
    steps = lambda n: [{"request": {"method": "GET", "path": f"/bookings/PNR{n % 4000:04d}"}, "expect": {"status": 200}}]
    files = {f"cases/pack{f}.yaml": yaml.safe_dump({"feature": f"Pack {f}", "cases": [
        {"id": f"TC{f * 500 + i + 1:05d}", "title": f"case {f * 500 + i}", "steps": steps(f * 500 + i)}
        for i in range(500)]}) for f in range(10)}
    project = project_with(make_project, files)
    from qa_agent import checks
    report = checks.CheckReport(project.team)
    report.case_files = [checks.load_case_file(path) for path in project.case_files()]
    started = time.perf_counter()
    checks._duplicate_cases(project, report)
    assert time.perf_counter() - started < 1.0
    assert len(duplicates(report)) == 1000                       # n and n + 4000 share a PNR
