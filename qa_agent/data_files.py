"""Data files of data-driven cases: one run per row, a value per column ({{row.amount}})."""

import csv
import io
import json
from pathlib import Path


class DataFileError(Exception):
    """A data file is missing or can't be read."""


def _csv_text(path: Path) -> str:
    """A CSV as Excel saves it: UTF-8 with or without its byte-order mark, or Windows' own encoding."""
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def rows(path: Path) -> list[dict]:
    """Every row of a CSV, Excel or JSON data file, as text keyed by column (for trace, not for tests)."""
    if not path.is_file():
        raise DataFileError(f"{path}: no such data file")
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            return list(csv.DictReader(io.StringIO(_csv_text(path), newline="")))
        if suffix == ".xlsx":
            from openpyxl import load_workbook
            table = list(load_workbook(path, read_only=True, data_only=True).active.iter_rows(values_only=True))
            header = [str(cell).strip() for cell in table[0]] if table else []
            return [dict(zip(header, row)) for row in table[1:]]
        if suffix == ".json":
            found = json.loads(path.read_text(encoding="utf-8-sig"))
            return found if isinstance(found, list) else []
    except (OSError, ValueError) as error:
        raise DataFileError(f"{path}: can't be read ({error})") from error
    raise DataFileError(f"{path}: use a .csv, .xlsx or .json data file")


def column_names(path: Path) -> list[str]:
    """The columns of a CSV, Excel or JSON (a list of objects) data file."""
    if not path.is_file():
        raise DataFileError(f"{path}: no such data file")
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            return [name.strip() for name in next(csv.reader(io.StringIO(_csv_text(path), newline="")), [])]
        if suffix == ".xlsx":
            from openpyxl import load_workbook
            sheet = load_workbook(path, read_only=True).active
            header = next(sheet.iter_rows(values_only=True), ())
            return [str(cell).strip() for cell in header if cell is not None]
        if suffix == ".json":
            rows = json.loads(path.read_text(encoding="utf-8-sig"))
            return list(rows[0]) if isinstance(rows, list) and rows and isinstance(rows[0], dict) else []
    except (OSError, ValueError) as error:
        raise DataFileError(f"{path}: can't be read ({error})") from error
    raise DataFileError(f"{path}: use a .csv, .xlsx or .json data file")
