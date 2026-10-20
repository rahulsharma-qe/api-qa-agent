"""Planted bugs: small slips a developer makes, switched on one at a time, so `qa-agent bugs` can
measure whether a suite catches bugs or only passes.

Off unless asked:  python -m mock_service --bug refund-boundary   (or MOCK_BUG=refund-boundary).
The OpenAPI description is always the one without bugs.
"""

BUGS = {
    "refund-boundary": "a cancel at exactly 24 hours gets no refund (< instead of <=)",
    "wrong-refund-amount": "the refund is half the amount",
    "second-cancel-allowed": "cancelling twice succeeds",
    "deleted-still-readable": "a deleted booking still reads back",
    "amount-changeable": "the amount can be changed after booking",
    "token-not-checked": "a call with no token is let through",
    "status-filter-ignored": "listing by status returns every booking",
}


class UnknownBug(ValueError):
    """Not one of the planted bugs."""


def checked(name: str) -> str:
    """The bug's name, or '' for none; an unknown name is refused with the list."""
    if name and name not in BUGS:
        raise UnknownBug(f"no planted bug '{name}' (use one of: {', '.join(BUGS)})")
    return name or ""
