"""The case format: loading, every shape problem reported at once, saving, the fingerprint."""

from pathlib import Path

import pytest

from qa_agent.cases import CaseFormatError, load_case_file, parse_case_file, save_case_file

GOOD = {"feature": "Cancellation", "cases": [{
    "id": "TC1", "title": "Cancel", "criteria": ["AC-2"], "priority": "P1",
    "steps": [{"request": {"method": "post", "path": "/bookings", "body": {"amount": 250}},
               "expect": {"status": 201}, "capture": {"pnr": "pnr"}},
              {"request": {"method": "POST", "path": "/bookings/{{pnr}}/cancel"},
               "expect": {"status": 200, "fields": {"refund_amount": 250}}}]}]}


def test_a_case_file_loads_into_cases_and_steps():
    case_file = parse_case_file(GOOD, Path("cases/cancellation.yaml"))
    case = case_file.cases[0]
    assert case_file.feature == "Cancellation"
    assert (case.id, case.priority, case.suite, case.review.status) == ("TC1", "P1", "functional", "draft")
    assert case.steps[0].request.method == "POST"                # upper-cased
    assert case.steps[0].capture == {"pnr": "pnr"}
    assert case.steps[1].expect["fields"] == {"refund_amount": 250}


def test_every_problem_is_reported_at_once():
    bad = {"feature": "x", "cases": [
        {"id": "TC1", "title": "t", "priority": "P9", "steps": [
            {"request": {"method": "FETCH", "path": "bookings"}, "expect": {"status": "ok", "colour": 1},
             "capture": {"unique": "x"}}]},
        {"id": "TC1", "title": "again"},
        {"title": "no id"}]}
    with pytest.raises(CaseFormatError) as raised:
        parse_case_file(bad, Path("cases/x.yaml"))
    problems = "\n".join(raised.value.problems)
    for expected in ("priority 'P9'", "method 'FETCH'", "path 'bookings' must start with /",
                     "expect 'status' should be a status code", "unknown key 'colour'",
                     "capture name 'unique'", "the id is used twice", "case 3: needs an 'id'"):
        assert expected in problems


def test_a_data_driven_status_may_come_from_the_data():
    data = {"feature": "x", "cases": [{"id": "TC1", "title": "t", "data_file": "data/rows.csv", "steps": [
        {"request": {"method": "GET", "path": "/x"}, "expect": {"status": "{{row.expected_status}}"}}]}]}
    assert parse_case_file(data, Path("x.yaml")).cases[0].steps[0].expect["status"] == "{{row.expected_status}}"


def test_saving_and_loading_gives_the_same_cases(tmp_path):
    case_file = parse_case_file(GOOD, tmp_path / "cancellation.yaml")
    save_case_file(case_file)
    again = load_case_file(tmp_path / "cancellation.yaml")
    assert again.to_dict() == case_file.to_dict()
    assert "{{pnr}}" in (tmp_path / "cancellation.yaml").read_text()


def test_the_fingerprint_changes_with_the_steps_not_with_the_title():
    case = parse_case_file(GOOD, Path("x.yaml")).cases[0]
    original = case.fingerprint()
    case.title, case.priority = "A new title", "P0"
    assert case.fingerprint() == original
    case.steps[1].expect["fields"]["refund_amount"] = 0
    assert case.fingerprint() != original


def test_an_approved_case_edited_afterwards_is_no_longer_approved():
    case = parse_case_file(GOOD, Path("x.yaml")).cases[0]
    case.review.status, case.review.fingerprint = "approved", case.fingerprint()
    assert case.is_approved and not case.changed_after_approval
    case.steps[0].request.body = {"amount": 1}
    assert not case.is_approved and case.changed_after_approval


def test_a_case_in_words_only_needs_steps():
    data = {"feature": "x", "cases": [{"id": "TC1", "title": "t", "manual_steps": "Make a booking. Cancel it."}]}
    case = parse_case_file(data, Path("x.yaml")).cases[0]
    assert case.needs_steps and case.manual_steps == ["Make a booking. Cancel it."]


def test_renaming_a_field_keeps_every_approval():
    """Fingerprints taken before a field was renamed (steps_text -> manual_steps) still match: a rename in
    the case format must not send approved cases back to review."""
    data = {"feature": "x", "cases": [{"id": "TC1", "title": "t", "manual_steps": ["Make a booking", "Cancel it"]}]}
    cases = parse_case_file(data, Path("x.yaml")).cases
    assert [case.fingerprint() for case in cases] == ["d0b0821d2e7f"]


def test_renaming_an_expectation_or_the_data_file_keeps_every_approval():
    """Taken before data -> data_file and within_ms -> max_response_ms: still the same fingerprint."""
    data = {"feature": "x", "cases": [{"id": "TC2", "title": "t", "data_file": "rows.csv", "steps": [
        {"request": {"method": "GET", "path": "/bookings/{{row.pnr}}"},
         "expect": {"status": 200, "max_response_ms": 2000}}]}]}
    cases = parse_case_file(data, Path("x.yaml")).cases
    for case in cases:
        case.project_root = None                     # the format alone: the data file's contents are added below
    assert [case.fingerprint() for case in cases] == ["ebf305a4de5c"]


def test_a_changed_row_in_the_data_file_sends_an_approved_case_back_to_review(tmp_path):
    """The expected results of a data-driven case live in its data file: editing a row is editing the case."""
    (tmp_path / "qa-agent.yaml").write_text("team: t\n")
    (tmp_path / "data").mkdir()
    (tmp_path / "cases").mkdir()
    rows = tmp_path / "data" / "refunds.csv"
    rows.write_text("hours,refund\n24,true\n25,false\n")
    (tmp_path / "cases" / "refunds.yaml").write_text(
        "feature: Refunds\ncases:\n  - id: TC1\n    title: Refund by hours\n    data_file: data/refunds.csv\n"
        "    steps:\n      - request: {method: GET, path: /refund}\n        expect: {status: 200}\n")
    case_file = load_case_file(tmp_path / "cases" / "refunds.yaml")
    case = case_file.cases[0]
    case.review.status, case.review.fingerprint = "approved", case.fingerprint()
    save_case_file(case_file)
    rows.write_bytes(b"hours,refund\r\n24,true\r\n25,false\r\n")              # saved on Windows: the same data
    assert load_case_file(tmp_path / "cases" / "refunds.yaml").cases[0].is_approved
    rows.write_bytes(b"\xef\xbb\xbfhours,refund\n24,true\n25,false\n")         # Excel's "CSV UTF-8": the same data
    assert load_case_file(tmp_path / "cases" / "refunds.yaml").cases[0].is_approved
    rows.write_text("hours,refund\n24,false\n25,false\n")                    # the 24-hour rule changed
    assert load_case_file(tmp_path / "cases" / "refunds.yaml").cases[0].changed_after_approval
    rows.unlink()
    assert load_case_file(tmp_path / "cases" / "refunds.yaml").cases[0].changed_after_approval


def test_an_excel_data_file_saved_again_with_the_same_rows_stays_approved(tmp_path):
    from openpyxl import Workbook
    (tmp_path / "qa-agent.yaml").write_text("team: t\n")
    (tmp_path / "cases").mkdir()
    book = Workbook()
    book.active.append(["hours", "refund"])
    book.active.append([24, True])
    book.save(tmp_path / "refunds.xlsx")
    (tmp_path / "cases" / "refunds.yaml").write_text(
        "feature: Refunds\ncases:\n  - id: TC1\n    title: Refund by hours\n    data_file: refunds.xlsx\n"
        "    steps:\n      - request: {method: GET, path: /refund}\n        expect: {status: 200}\n")
    case_file = load_case_file(tmp_path / "cases" / "refunds.yaml")
    case_file.cases[0].review.status, case_file.cases[0].review.fingerprint = "approved", case_file.cases[0].fingerprint()
    save_case_file(case_file)
    book.properties.lastModifiedBy = "someone else"              # a re-save changes the bytes, not the rows
    book.save(tmp_path / "refunds.xlsx")
    assert load_case_file(tmp_path / "cases" / "refunds.yaml").cases[0].is_approved
    book.active["B2"] = False
    book.save(tmp_path / "refunds.xlsx")
    assert load_case_file(tmp_path / "cases" / "refunds.yaml").cases[0].changed_after_approval
