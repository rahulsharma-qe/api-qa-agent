"""`qa-agent import cases`: the team's existing cases, written into the project's case files.

Each imported case gets `review: {status: draft}` and its `source`. A case whose id is already in
the project is skipped and reported, unless --overwrite, which replaces it (and its review).
"""

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from qa_agent.cases import CaseFile, CaseFormatError, load_case_file, parse_case_file, save_case_file
from qa_agent.importers.common import CaseImportError, ImportResult, slug
from qa_agent.importers.gherkin import read_feature_file
from qa_agent.importers.postman import read_postman_collection
from qa_agent.importers.sheet_cases import read_sheet_cases
from qa_agent.project import TeamProject


@dataclass
class ImportSummary:
    written: dict = field(default_factory=dict)       # case file -> ids added or replaced
    skipped: list = field(default_factory=list)       # "TC003: already in cases/x.yaml"
    notes: list = field(default_factory=list)
    data_files: list = field(default_factory=list)
    new_ids: list = field(default_factory=list)       # "TC042: Health check": cases that came without an id

    def as_text(self) -> str:
        lines = [f"{file}: {', '.join(ids)}" for file, ids in self.written.items()]
        lines += [f"new id {item}" for item in self.new_ids]
        lines += [f"data file written: {name}" for name in self.data_files]
        lines += [f"skipped {item}" for item in self.skipped]
        lines += [f"note: {note}" for note in self.notes]
        total = sum(len(ids) for ids in self.written.values())
        lines.append(f"{total} cases imported as drafts, {len(self.skipped)} skipped")
        return "\n".join(lines)


def read_existing_cases(path: Path, source_name: str) -> ImportResult:
    """Any supported file -> features of case dicts. The format is chosen by the file's type."""
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".csv"):
        return read_sheet_cases(path, source_name)
    if suffix == ".json":
        return read_postman_collection(path, source_name)
    if suffix == ".feature":
        return read_feature_file(path, source_name)
    raise CaseImportError(f"{path}: use Excel (.xlsx), CSV, a Postman collection (.json) or Gherkin (.feature)")


def import_cases(project: TeamProject, paths: list[Path], into: Optional[Path] = None,
                 overwrite: bool = False) -> ImportSummary:
    summary = ImportSummary()
    try:
        files = {path: load_case_file(path) for path in project.case_files()}
    except CaseFormatError as error:
        raise CaseImportError(f"{project.relative(error.path)} can't be read; fix it first (qa-agent check "
                              f"lists the problems)") from error
    read = []
    for path in paths:                                   # every file first, so new ids don't depend on the order
        result = read_existing_cases(path, project.relative(path))
        summary.notes += result.notes
        read += result.features
    next_id = id_maker(project, files, read)
    sources = {_source_key(case.source): case.id for case_file in files.values() for case in case_file.cases
               if case.source}
    for feature in read:
        target = Path(into) if into else project.cases_dir / f"{slug(feature.feature)}.yaml"
        target = target if target.is_absolute() else project.root / target
        case_file = files.setdefault(target, CaseFile(target, feature.feature, []))
        for raw in feature.cases:
            raw = dict(raw)
            if not raw.get("id"):
                known = sources.get(_source_key(raw.get("source")))       # imported before: keep its id
                raw["id"] = known or next_id()
                if not known:
                    summary.new_ids.append(f"{raw['id']}: {raw.get('title')}")
            rows = raw.pop("_data_rows", None)
            if rows:
                raw["data_file"] = f"data/{slug(feature.feature)}-{raw['id'].lower()}.csv"
            if _add_case(raw, case_file, files, overwrite, project, summary) and rows:
                _write_data_file(project.root / raw["data_file"], rows, overwrite, summary, raw["data_file"])
    for case_file in files.values():
        if project.relative(case_file.path) in summary.written:
            save_case_file(case_file)
    return summary


def _source_key(source) -> str:
    return json.dumps(source or {}, sort_keys=True)


def id_maker(project: TeamProject, files: dict, read: list):
    """The next free id with the project's prefix: after TC041 comes TC042, whatever order files came in."""
    prefix = project.case_id_prefix
    pattern = re.compile(rf"^{re.escape(prefix)}-?(\d+)$", re.IGNORECASE)
    used = [case.id for case_file in files.values() for case in case_file.cases]
    used += [str(raw["id"]) for feature in read for raw in feature.cases if raw.get("id")]
    numbers = [int(match.group(1)) for match in map(pattern.match, used) if match]
    counter = {"next": max(numbers, default=0) + 1}

    def next_id() -> str:
        value = f"{prefix}{counter['next']:03d}"
        counter["next"] += 1
        return value
    return next_id


def _add_case(raw: dict, case_file: CaseFile, files: dict, overwrite: bool, project: TeamProject,
              summary: ImportSummary) -> bool:
    raw = {**raw, "review": {"status": "draft"}}
    try:
        case = parse_case_file({"feature": case_file.feature, "cases": [raw]}, case_file.path).cases[0]
    except CaseFormatError as error:
        summary.skipped.append(f"{raw.get('id')}: " + "; ".join(error.problems))
        return False
    holder = next((f for f in files.values() if any(c.id == case.id for c in f.cases)), None)
    if holder is not None and not overwrite:
        summary.skipped.append(f"{case.id}: already in {project.relative(holder.path)} (use --overwrite to replace it)")
        return False
    if holder is not None:
        holder.cases[[c.id for c in holder.cases].index(case.id)] = case
        case_file = holder
    else:
        case_file.cases.append(case)
    summary.written.setdefault(project.relative(case_file.path), []).append(case.id)
    return True


def _write_data_file(path: Path, rows: list[dict], overwrite: bool, summary: ImportSummary, name: str) -> None:
    if path.exists() and not overwrite:
        summary.skipped.append(f"data file {name}: already there (use --overwrite to replace it)")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary.data_files.append(name)
