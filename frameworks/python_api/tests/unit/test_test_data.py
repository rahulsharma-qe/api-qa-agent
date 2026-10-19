import json

from openpyxl import Workbook

from api_test_framework import load_rows, new_passenger


def test_csv_cells_become_numbers_booleans_and_none(tmp_path):
    path = tmp_path / "rows.csv"
    path.write_text("case,amount,refund,ratio,note\nexactly 24h,250,true,0.5,\n")
    assert load_rows(path) == [{"case": "exactly 24h", "amount": 250, "refund": True, "ratio": 0.5, "note": None}]


def test_json_as_a_list_or_under_rows(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps([{"a": 1}]))
    (tmp_path / "b.json").write_text(json.dumps({"rows": [{"b": "2"}]}))
    assert load_rows(tmp_path / "a.json") == [{"a": 1}] and load_rows(tmp_path / "b.json") == [{"b": "2"}]


def test_excel_first_row_is_the_header(tmp_path):
    book = Workbook()
    book.active.append(["case", "amount", "refund"])
    book.active.append(["late", 250, "false"])
    book.active.append([None, None, None])           # an empty row is skipped
    book.save(tmp_path / "rows.xlsx")
    assert load_rows(tmp_path / "rows.xlsx") == [{"case": "late", "amount": 250, "refund": False}]


def test_new_passengers_never_clash_and_use_a_test_domain():
    first, second = new_passenger(), new_passenger()
    assert first != second and first["email"].endswith("@testdata.example")
