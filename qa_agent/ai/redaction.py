"""What leaves for a model is redacted first, by these rules and no others:

    tokens      Bearer, Basic and Token values, JWTs
    keys        sk-/pk-/rk- keys, GitHub tokens (ghp_...), AWS access key ids (AKIA...)
    secrets     the value after password, passwd, secret, client_secret, api_key or apikey; and after
                x-api-key, api-key, access_token, refresh_token, id_token, auth_token, private_key or token
                when the value has a digit (so `capture: {token: access_token}`, a field name, stays)
    cards       13 to 19 digits that pass the Luhn check, after a key named for a card (card, card_number,
                credit_card, pan), or written in groups of four (4111 1111 1111 1111)
    phones      10-digit mobile numbers after a key named for a phone (phone, phone_number, mobile,
                msisdn, contact_number), +91 mobile numbers anywhere, and any number written with a
                + country code and 11 to 15 digits in all (+44 20 7946 0958)
    emails      any email address

Key names are matched whole: card_id, contact_id or phone_verified_at hold an id or a time, and stay.

What these rules don't catch, said plainly: a bare long number (an id, an amount, a number in a path,
and so also a card or a phone written in a sentence: "my card 4111111111111111", "call 9876543210"), phone
numbers in other countries' local formats ((987) 654-3210, 080 4123 4567), cards grouped other than in
fours (3782 822463 10005), and any secret in a shape not listed here. By its digits alone a number can't be
told from an id, and redacting ids would hide what the test is about.

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
# Whole key names only: card_id or phone_verified_at holds an id or a time, not a card or a phone.
CARD_KEYS = r"card|card_?(?:number|no)|(?:credit|debit)_?card(?:_?number)?|cc_?(?:number|no)|pan|pan_?number"
PHONE_KEYS = (r"phone|phone_?(?:number|no)|(?:mobile|cell|work|home|contact)_?phone|mobile|mobile_?(?:number|no)"
              r"|msisdn|contact_?(?:number|no)|whatsapp(?:_?number)?")
KEY = r"(?<![\w-])([\"']?(?:{names})[\"']?\s*[:=]\s*[\"']?)"
CARD_AFTER_KEY = re.compile(rf"(?i){KEY.format(names=CARD_KEYS)}(\d[\d -]{{11,22}}\d)(?![\w-])")
CARD_IN_GROUPS = re.compile(r"(?<![\w-])(?:\d{4}[ -]){2,3}\d{1,7}(?![\w-])")
PHONE_AFTER_KEY = re.compile(rf"(?i){KEY.format(names=PHONE_KEYS)}(?:\+?91[\s-]?|0)?\d{{5}}[\s-]?\d{{5}}(?![\w-])")
INTERNATIONAL = re.compile(r"(?<![\w+])\+\d{1,3}(?:[\s-]?\d{2,4}){2,4}(?![\w-])")   # +44 20 7946 0958
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
    ("phone", PHONE_AFTER_KEY, r"\1[phone]"),
    ("phone", re.compile(r"(?<![\w+])\+91[\s-]?[6-9]\d{4}[\s-]?\d{5}(?![\w-])"), "[phone]"),
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
        digits = re.sub(r"\D", "", match.group(match.lastindex or 0))
        if 13 <= len(digits) <= 19 and _luhn(digits):
            counts["card"] += 1
            return (match.group(1) if match.lastindex else "") + "[card]"
        return match.group(0)

    text = CARD_AFTER_KEY.sub(card, text)            # before phones: a card number holds phone-like runs
    text = CARD_IN_GROUPS.sub(card, text)
    for kind, pattern, replacement in RULES:
        text, found = pattern.subn(replacement, text)
        if found:
            counts[kind] += found

    def international(match):
        if 11 <= len(re.sub(r"\D", "", match.group(0))) <= 15:      # "+100 200 3000" is an amount, not a phone
            counts["phone"] += 1
            return "[phone]"
        return match.group(0)

    text = INTERNATIONAL.sub(international, text)
    return Redacted(text, counts)
