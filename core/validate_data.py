"""Hybrid validation.

Rules (deterministic, free, 100% reliable) handle facts: format, length, duplicates, range.
An LLM is used ONLY for the judgment call: does the dataset have genuine variety?
Knowing when NOT to use AI matters as much as knowing when to.
"""
import re
import json
from .llm import get_client, extract_json

_PNR = re.compile(r"^[A-Z0-9]{6}$")
_EMAIL = re.compile(r"^[^@\s]+@testdata\.example$")


def validate_data_rules(records):
    """Deterministic checks only. No LLM. Returns a list of concrete violations."""
    issues, seen = [], set()
    for r in records:
        rid = r.get("id", "?")
        if not _PNR.match(r.get("pnr", "")):
            issues.append(f"[{rid}] PNR '{r.get('pnr')}' fails 6-char uppercase-alphanumeric rule")
        if r.get("pnr") in seen:
            issues.append(f"[{rid}] duplicate PNR '{r.get('pnr')}'")
        seen.add(r.get("pnr"))
        if not _EMAIL.match(r.get("email", "")):
            issues.append(f"[{rid}] email '{r.get('email')}' is not a @testdata.example address")
        amt = r.get("amount")
        if not isinstance(amt, (int, float)) or amt < 0:
            issues.append(f"[{rid}] amount '{amt}' invalid (must be number >= 0)")
        if r.get("category") not in {"valid", "edge", "adversarial"}:
            issues.append(f"[{rid}] category '{r.get('category')}' not in valid/edge/adversarial")
    return issues


def validate_data_llm(records, client=None):
    """Judgment-only check: genuine variety? This is where an LLM earns its place."""
    client = client or get_client()
    system = (
        "You are a QA data reviewer. Judge ONLY whether this dataset has genuine variety and "
        "edge coverage. Return ONLY JSON, no fences: {variety:'good'|'weak', notes:[..]}."
    )
    return extract_json(client.complete(system, json.dumps(records, indent=2), max_tokens=800))


def validate_data(records, client=None, use_llm=True):
    """Combined gate. Returns (passed, rule_issues, llm_judgment)."""
    rule_issues = validate_data_rules(records)
    llm_judgment = validate_data_llm(records, client=client) if use_llm else {"variety": "skipped", "notes": []}
    passed = (len(rule_issues) == 0) and (llm_judgment["variety"] in ("good", "skipped"))
    return passed, rule_issues, llm_judgment
