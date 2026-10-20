"""Reading and writing the YAML files qa-agent owns, in one readable layout.

Short mappings and lists of plain values are written on one line ({method: POST, path: /bookings});
everything else is written as blocks. Comments are not kept when qa-agent rewrites a file, which is
why cases have a `notes` field.
"""

import datetime
import json
from pathlib import Path
from typing import Any

import yaml

ONE_LINE_LIMIT = 90


class FileFormatError(Exception):
    """A file qa-agent reads is not valid YAML or JSON, or not the shape expected."""


def read_yaml(path: Path) -> Any:
    try:
        return _plain(yaml.safe_load(path.read_text(encoding="utf-8")))
    except yaml.YAMLError as error:
        raise FileFormatError(f"{path}: not valid YAML ({error})") from error


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, Dumper=_ReadableDumper, sort_keys=False, allow_unicode=True, width=110),
                    encoding="utf-8")


def _plain(value: Any) -> Any:
    """Dates become text, so a value reads back exactly as it was written."""
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def _is_short_and_flat(value: Any) -> bool:
    items = value.values() if isinstance(value, dict) else value
    if any(isinstance(item, (dict, list)) and item for item in items):
        return False
    return len(json.dumps(value, default=str)) <= ONE_LINE_LIMIT


class _ReadableDumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)      # list items indented under their key


def _represent_dict(dumper: yaml.SafeDumper, value: dict):
    return dumper.represent_mapping("tag:yaml.org,2002:map", value.items(), flow_style=_is_short_and_flat(value))


def _represent_list(dumper: yaml.SafeDumper, value: list):
    return dumper.represent_sequence("tag:yaml.org,2002:seq", value, flow_style=_is_short_and_flat(value))


_ReadableDumper.add_representer(dict, _represent_dict)
_ReadableDumper.add_representer(list, _represent_list)
