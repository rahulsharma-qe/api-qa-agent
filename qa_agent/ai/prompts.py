"""What the model is told. The rules here ask; the code after the reply checks (drafting.py):
nothing below is trusted just because the prompt says it."""

from typing import Optional

import yaml

DRAFT_CASES_SYSTEM = """You draft API test cases for a QA team, as data in the team's case format.
A person reviews every case before it becomes a test.

Rules:
1. Draft only for the gap you are given: one behaviour per case, one to three cases.
2. Use only the operations listed, with the method and path exactly as listed. A value in a path is
   {{name}}, captured in an earlier step, or data the case creates first.
3. Check what the response says, not only the status: add fields, exists or types to the step
   that matters.
4. Where the API needs unique data (a name, an email), use {{unique}} in it.
5. Capture a value with capture: {name: path.in.the.response} and use it later as {{name}}.
6. Never invent an expected value that the criterion, the API or the examples don't give you: write
   TBD in its place and say in notes what has to be confirmed.
7. If the gap can't be tested with these operations, reply with cases: [] and a top-level reason.
8. Don't write id, review, source or suite: the tool adds them.
9. A case that tests a limit (exactly at a boundary, the largest value allowed) has the tag edge.

Reply with YAML only, in this shape:

cases:
  - title: A cancelled order reads back as cancelled
    criteria: [AC-4]              # ids from the acceptance criteria given; [] if none applies
    priority: P1                  # P0 (critical) to P3
    tags: [orders]                # optional; edge too, for a case at a limit (rule 9)
    steps:
      - request: {method: POST, path: /orders, body: {customer: "C {{unique}}", amount: 120}}
        expect: {status: 201, exists: [id]}
        capture: {order_id: id}
      - request: {method: POST, path: "/orders/{{order_id}}/cancel"}
        expect: {status: 200}
      - request: {method: GET, path: "/orders/{{order_id}}"}
        expect: {status: 200, fields: {status: cancelled}}
    notes: optional; what a reviewer should know

A step's request: method, path, and optionally query, headers, body, service, auth (none for a call
without a token). Its expect: status, and optionally fields (path: value), exists (paths),
types (path: string, number, integer, boolean, list, object or null), contains (path: text),
list_length, list_contains, list_excludes (path: {field: value}), headers, max_response_ms.
"""


def draft_cases_user(gap, criteria: dict, operations: list, examples: list, team_rules: str,
                     sent_back: Optional[dict] = None) -> str:
    what = f"What the draft was for: {gap.describe_for_redo()}" if sent_back else f"The gap: {gap.describe()}"
    parts = [what, "", "Acceptance criteria:"]
    parts += [f"- {criterion.id}: {criterion.text}" for criterion in criteria.values()] or ["(none)"]
    parts += ["", f"The API (service {gap.service or 'main'}):"]
    for operation in operations:
        body = f" · required body fields: {', '.join(operation.body_required)}" if operation.body_required else ""
        codes = ", ".join(str(code) for code in operation.responses)
        parts.append(f"- {operation.method} {operation.path}{f' ({operation.summary})' if operation.summary else ''}"
                     f" · responses: {codes}{body}")
    if examples:
        parts += ["", "Approved cases from this team, for the style:", "",
                  yaml.safe_dump({"cases": examples}, sort_keys=False, allow_unicode=True).rstrip()]
    if team_rules.strip():
        parts += ["", "The team's own rules:", team_rules.strip()]
    if sent_back:
        parts += ["", "A reviewer sent back an earlier draft for this gap:", "",
                  yaml.safe_dump({"cases": [sent_back["case"]]}, sort_keys=False, allow_unicode=True).rstrip(),
                  "", f"The reviewer's comment: {sent_back['comment'] or '(none)'}",
                  "Write a new draft that does what the comment asks. Don't repeat what the reviewer sent back."]
    return "\n".join(parts) + "\n"


DRAFT_CRITERIA_SYSTEM = """You turn a product requirement, written in plain words, into acceptance criteria a QA team can test.
A person reviews every criterion and question before anything is tested.

Rules:
1. One criterion is one testable behaviour, in one sentence, in the requirement's own terms.
2. Every criterion and every question quotes, in "from", the exact words of the requirement it comes
   from (copy them; a short phrase is enough). Never add a behaviour the requirement doesn't state.
3. Ask instead of guessing. Write a question when:
   - ambiguity: a rule can be read two ways, or its boundary isn't settled (what happens at exactly
     24 hours?);
   - omission: something a tester needs isn't said at all (what if the payment fails? is there a limit?);
   - contradiction: two parts of the requirement say different things (24 hours here, one working day
     there); quote one of them in "from" and name the other in the text;
   - dependency: the behaviour depends on another feature or system the requirement doesn't describe.
4. Don't write ids or status: the tool adds them.

Reply with YAML only, in this shape:

criteria:
  - text: An order cancelled within 24 hours of being placed is refunded in full.
    from: "cancel within 24 hours for a full refund"
questions:
  - kind: ambiguity
    text: Is an order cancelled at exactly 24 hours refunded?
    from: "within 24 hours"
"""


def draft_criteria_user(requirement_name: str, requirement: str, existing: dict, changed: tuple = ()) -> str:
    parts = [f"The requirement ({requirement_name}):", "", requirement.strip(), ""]
    if existing:
        parts += ["Acceptance criteria the team already has (don't repeat them):"]
        parts += [f"- {criterion.id}: {criterion.text}" for criterion in existing.values()]
    if changed:
        parts += ["", "These criteria quote words that are no longer in the requirement. Where the requirement "
                  "now says something else about the same behaviour, draft the criterion as it reads now:"]
        parts += [f"- {key}: {text}" for key, text in changed]
    return "\n".join(parts) + "\n"
