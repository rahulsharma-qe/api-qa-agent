"""What leaves for a model is redacted first: emails, tokens, keys and secret values.

The AI layer sends the API's structure and approved cases as examples. Example data can still hold
a real email or a pasted token; redaction replaces each with a label before anything is sent, and
counts what it replaced (the audit log keeps the counts). Placeholders such as {{unique}} and field
names such as email stay: they say what to test, not who.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

SECRET_KEYS = r"password|passwd|secret|client_secret|api_key|apikey"     # tokens are caught by their shape, below

RULES = (                                            # (kind, pattern, replacement), applied in this order
    ("token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer [token]"),
    ("token", re.compile(r"(?i)\bbasic\s+[A-Za-z0-9+/]{8,}={0,2}"), "Basic [token]"),
    ("token", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), "[token]"),
    ("key", re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}\b"), "[key]"),
    ("key", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "[key]"),
    ("key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[key]"),
    ("secret", re.compile(rf"(?i)([\"']?(?:{SECRET_KEYS})[\"']?\s*[:=]\s*)([\"']?)(?!\[|\{{)[^\s\"',}}]+\2"), r"\1\2[secret]\2"),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[email]"),
)


@dataclass
class Redacted:
    text: str
    counts: Counter = field(default_factory=Counter)      # kind -> how many were replaced


def redact(text: str) -> Redacted:
    counts: Counter = Counter()
    for kind, pattern, replacement in RULES:
        text, found = pattern.subn(replacement, text)
        if found:
            counts[kind] += found
    return Redacted(text, counts)
