"""What teams' files really look like: Postman folders by feature, Gherkin with several Examples tables,
Excel's own CSV, damaged files, and a pasted secret."""

import json

import pytest

from qa_agent.cli import main
from qa_agent.importers.common import CaseImportError
from qa_agent.importers.gherkin import read_feature_file
from qa_agent.importers.postman import read_postman_collection
from qa_agent.importers.sheet_cases import read_sheet_cases

SCHEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"


def test_a_postman_folder_by_feature_is_a_group_of_cases_each_with_its_own_id(tmp_path):
    path = tmp_path / "c.postman_collection.json"
    path.write_text(json.dumps({"info": {"name": "Bookings", "schema": SCHEMA}, "item": [
        {"name": "Bookings", "item": [
            {"name": "TC300 Read a booking", "request": {"method": "GET", "url": "{{baseUrl}}/bookings/AB12CD"}},
            {"name": "TC301 Delete a booking", "request": {"method": "DELETE", "url": "{{baseUrl}}/bookings/AB12CD"}},
            {"name": "TC310 Create and cancel", "item": [
                {"name": "Create", "request": {"method": "POST", "url": "{{baseUrl}}/bookings"}},
                {"name": "Cancel", "request": {"method": "POST", "url": "{{baseUrl}}/bookings/AB12CD/cancel"}}]}]}]}))
    cases = read_postman_collection(path, "existing/c.json").features[0].cases
    assert [(case["id"], case["title"], len(case["steps"])) for case in cases] == [
        ("TC310", "Create and cancel", 2), ("TC300", "Read a booking", 1), ("TC301", "Delete a booking", 1)]


OUTLINE = '''Feature: Refunds

  @TC400
  Scenario Outline: Read a booking
    When I GET "/bookings/<pnr>"
    Then the status is <status>

    Examples: present
      | pnr    | status |
      | AB12CD | 200    |

    Examples: gone
      | pnr    | status |
      | ZZ99ZZ | 404    |

    Examples: other columns
      | code | status |
      | X    | 400    |
'''


def test_several_examples_tables_give_one_data_file_with_one_header(tmp_path):
    path = tmp_path / "refunds.feature"
    path.write_text(OUTLINE)
    result = read_feature_file(path, "existing/refunds.feature")
    case = result.features[0].cases[0]
    assert case["_data_rows"] == [{"pnr": "AB12CD", "status": "200"}, {"pnr": "ZZ99ZZ", "status": "404"}]
    assert any("Examples table 3 has other columns (code, status)" in note for note in result.notes)


def test_a_csv_saved_by_excel_in_its_own_encoding_is_read(tmp_path):
    path = tmp_path / "cases.csv"
    path.write_bytes("ID,Title,Method,Path,Expected Status\nTC500,Café booking – read,GET,/bookings/1,200\n"
                     .encode("cp1252"))
    case = read_sheet_cases(path, "existing/cases.csv").features[0].cases[0]
    assert case["title"] == "Café booking – read"


def test_a_damaged_excel_file_is_a_message_not_a_traceback(tmp_path, make_project, capsys):
    broken = tmp_path / "cases.xlsx"
    broken.write_bytes(b"this is not a zip file")
    with pytest.raises(CaseImportError, match="can't be opened as an Excel file .BadZipFile.: .*save it again as .xlsx"):
        read_sheet_cases(broken, "existing/cases.xlsx")
    root = make_project({"cases/a.yaml": "feature: A\ncases: []\n", "review/cases.xlsx": "not a zip"})
    assert main(["--project", str(root), "review", "apply"]) == 2
    assert "can't be opened as an Excel sheet" in capsys.readouterr().err


def test_check_warns_about_a_secret_written_into_a_case(make_project, capsys):
    root = make_project({"cases/a.yaml": """
feature: A
cases:
  - id: TC1
    title: Read with a key
    criteria: []
    steps:
      - request: {method: GET, path: /bookings, headers: {X-Api-Key: sk-live-SECRET1234567890}}
        expect: {status: 200}
"""})
    main(["--project", str(root), "check"])
    out = capsys.readouterr().out
    assert "a key is written into the case, and case files are committed" in out
    assert "SECRET1234567890" not in out
