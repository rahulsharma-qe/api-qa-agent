"""Excel and CSV cases: the API layout (runnable steps) and the manual layout (steps in words)."""

import pytest
from openpyxl import Workbook

from qa_agent.importers.common import CaseImportError
from qa_agent.importers.sheet_cases import read_sheet_cases

API_HEADER = ["Case ID", "Title", "Criteria", "Priority", "Tags", "Step", "Method", "Path", "Body",
              "Expected Status", "Expected Fields", "Capture"]


def workbook(path, title, rows):
    book = Workbook()
    sheet = book.active
    sheet.title = title
    for row in rows:
        sheet.append(row)
    book.save(path)
    return path


def test_the_api_layout_gives_steps_with_requests_expectations_and_captures(tmp_path):
    path = workbook(tmp_path / "cases.xlsx", "Bookings API", [API_HEADER,
        ["TC1", "Create and read", "AC-1, AC-2", "High", "smoke", 1, "post", "/bookings", '{"amount": 250}', 201,
         "status=active", "pnr=pnr"],
        [None, None, None, None, None, 2, "GET", "/bookings/{{pnr}}?full=true", None, 200, "amount=250; paid=true", None],
        ["TC2", "Delete", "AC-1", "Critical", None, 1, "DELETE", "/bookings/X1", None, 204, None, None]])
    result = read_sheet_cases(path, "existing/cases.xlsx")
    feature = result.features[0]
    assert feature.feature == "Bookings API"
    first, second = feature.cases
    assert (first["id"], first["criteria"], first["priority"], first["tags"]) == ("TC1", ["AC-1", "AC-2"], "P1", ["smoke"])
    assert first["steps"][0] == {"request": {"method": "POST", "path": "/bookings", "body": {"amount": 250}},
                                 "expect": {"status": 201, "fields": {"status": "active"}}, "capture": {"pnr": "pnr"}}
    assert first["steps"][1]["request"] == {"method": "GET", "path": "/bookings/{{pnr}}", "query": {"full": "true"}}
    assert first["steps"][1]["expect"]["fields"] == {"amount": 250, "paid": True}
    assert first["source"] == {"format": "excel-api", "file": "existing/cases.xlsx", "sheet": "Bookings API", "row": 2}
    assert second["priority"] == "P0"


def test_the_manual_layout_keeps_the_steps_in_words(tmp_path):
    path = tmp_path / "refunds.csv"
    path.write_text("ID,Title,Preconditions,Steps,Expected Result,Priority,Criteria\n"
                    'TC20,Late cancel,A booking made two days ago,"1. Cancel it 2. Open the refund status",'
                    "Status is no_refund,Low,AC-5\n", encoding="utf-8")
    case = read_sheet_cases(path, "existing/refunds.csv").features[0].cases[0]
    assert case["steps_text"] == ["Before: A booking made two days ago", "Cancel it", "Open the refund status",
                                  "Expected: Status is no_refund"]
    assert (case["priority"], case["criteria"], case["source"]["format"]) == ("P3", ["AC-5"], "csv-manual")
    assert "steps" not in case


def test_rows_that_cant_be_read_are_reported_not_guessed(tmp_path):
    path = workbook(tmp_path / "cases.xlsx", "S", [API_HEADER,
        [None, None, None, None, None, 1, "GET", "/x", None, 200, None, None],
        ["TC1", "t", "AC-1", "Someday", None, 1, "POST", "/x", "{not json", 201, None, None],
        [None, None, None, None, None, 2, None, None, None, None, None, None]])
    result = read_sheet_cases(path, "cases.xlsx")
    notes = "\n".join(result.notes)
    assert "row 2: no Case ID and no case above it" in notes
    assert "priority 'Someday' is not one qa-agent knows; set to P2" in notes
    assert "Body is not JSON; kept as text" in notes
    assert len(result.features[0].cases[0]["steps"]) == 1


def test_a_sheet_in_neither_layout_is_refused(tmp_path):
    path = workbook(tmp_path / "x.xlsx", "S", [["Name", "Owner"], ["a", "b"]])
    with pytest.raises(CaseImportError, match="neither Method and Path"):
        read_sheet_cases(path, "x.xlsx")
