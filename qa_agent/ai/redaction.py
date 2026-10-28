"""What leaves for a model is redacted first, by these rules and no others:

    tokens      Bearer, Basic and Token values, JWTs
    keys        sk-/pk-/rk- keys, GitHub tokens (ghp_...), AWS access key ids (AKIA...)
    secrets     the value after password, passwd, secret, client_secret, api_key or apikey; and after
                x-api-key, api-key, access_token, refresh_token, id_token, auth_token, private_key or token
                when the value has a digit (so `capture: {token: access_token}`, a field name, stays)
    cards       card numbers (13 to 19 digits that pass the Luhn check)
    phones      Indian mobile numbers, with or without +91, and numbers written with a + country code
    emails      any email address


The AI layer sends the API's structure and approved cases as examples. Example data can still hold
a real email or a pasted token; redaction replaces each with a label before anything is sent, and
counts what it replaced (the audit log keeps the counts). Placeholders such as {{unique}} and field
names such as email stay: they say what to test, not who.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

SECRET_KEYS = r"password|passwd|secret|client_secret|api_key|apikey"     # tokens are caught by their shape, below
TOKEN_KEYS = r"x-api-key|api-key|access[_-]token|refresh[_-]token|id[_-]token|auth[_-]token|private[_-]key|token"
CARD = re.compile(r"(?<![\w-])(?:\d[ -]?){12,18}\d(?![\w-])")

RULES = (                                            # (kind, pattern, replacement), applied in this order
    ("token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer [token]"),
    ("token", re.compile(r"(?i)\bbasic\s+[A-Za-z0-9+/]{8,}={0,2}"), "Basic [token]"),
    ("token", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), "[token]"),
    ("token", re.compile(r"(?i)\btoken\s+(?=\S*\d)[A-Za-z0-9._~+/=-]{16,}"), "Token [token]"),
    ("key", re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}\b"), "[key]"),
    ("key", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "[key]"),
    ("key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[key]"),
    ("secret", re.compile(rf"(?i)([\"']?(?:{SECRET_KEYS})[\"']?\s*[:=]\s*)([\"']?)(?!\[|\{{)[^\s\"',}}]+\2"), r"\1\2[secret]\2"),
    ("secret", re.compile(rf"(?i)([\"']?(?:{TOKEN_KEYS})[\"']?\s*[:=]\s*)([\"']?)(?!\[|\{{)(?=[^\s\"',}}]*\d)"
                          rf"[^\s\"',}}]{{8,}}\2"), r"\1\2[secret]\2"),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[email]"),
    ("phone", re.compile(r"(?<![\w+])(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?![\w-])"), "[phone]"),
    ("phone", re.compile(r"(?<![\w+])\+\d{1,3}[\s-]?\d{2,4}[\s-]?\d{3,4}[\s-]?\d{3,4}(?![\w-])"), "[phone]"),
)


@dataclass
class Redacted:
    text: str
    counts: Counter = field(default_factory=Counter)      # kind -> how many were replaced


def _luhn(digits: str) -> bool:
    total = 0
    for index, digit in enumerate(reversed(digits)):
        value = int(digit) * (2 if index % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0


def redact(text: str) -> Redacted:
    counts: Counter = Counter()

    def card(match):
        digits = re.sub(r"\D", "", match.group(0))
        if 13 <= len(digits) <= 19 and _luhn(digits):
            counts["card"] += 1
            return "[card]"
        return match.group(0)

    text = CARD.sub(card, text)                      # before phones: a card number holds phone-like runs
    for kind, pattern, replacement in RULES:
        text, found = pattern.subn(replacement, text)
        if found:
            counts[kind] += found
    return Redacted(text, counts)
