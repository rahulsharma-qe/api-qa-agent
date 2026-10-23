"""qa-agent check: each rule, with the finding it gives."""

from qa_agent.checks import ERROR, INFO, WARNING, check_project
from qa_agent.project import TeamProject

from tests.qa_agent.conftest import API, CRITERIA

CASES = """
feature: Bookings
cases:
  - id: TC1
    title: good
    criteria: [AC-1]
    steps:
      - request: {method: POST, path: /bookings, body: {passenger_name: "A {{unique}}", email: a@b.c}}
        expect: {status: 201}
        capture: {pnr: pnr}
      - request: {method: GET, path: "/bookings/{{pnr}}"}
        expect: {status: 200, fields: {pnr: "{{pnr}}"}}
"""


def findings(project_root):
    report = check_project(TeamProject.load(project_root))
    return report, {(f.level, f.case_id, f.message.split(":")[0] if f.case_id else "") for f in report.findings}, \
        "\n".join(f.message for f in report.findings)


def test_a_good_case_has_no_findings(make_project):
    report, _, _ = findings(make_project({"api/api.yaml": API, "acceptance-criteria.yaml": CRITERIA, "cases/b.yaml": CASES}))
    assert report.findings == [] and not report.has_errors and len(report.cases) == 1


def test_values_used_before_capture_and_data_columns(make_project, tmp_path):
    root = make_project({"api/api.yaml": API, "acceptance-criteria.yaml": CRITERIA, "data/rows.csv": "amount,status\n1,201\n",
                         "cases/b.yaml": """
        feature: B
        cases:
          - id: TC1
            title: t
            criteria: [AC-1]
            steps:
              - request: {method: GET, path: "/bookings/{{pnr}}"}
                expect: {status: 200}
          - id: TC2
            title: t
            criteria: [AC-1]
            data_file: data/rows.csv
            steps:
              - request: {method: POST, path: /bookings, body: {passenger_name: x, email: y, amount: "{{row.amont}}"}}
                expect: {status: "{{row.status}}"}
          - id: TC3
            title: t
            criteria: [AC-1]
            steps:
              - request: {method: POST, path: /bookings, body: {passenger_name: x, email: y, amount: "{{row.amount}}"}}
                expect: {status: 201}
        """})
    report, _, text = findings(root)
    assert "TC1 step 1: {{pnr}} is used before it is captured" in text
    assert "TC2 step 1: {{row.amont}}: data/rows.csv has no column 'amont' (it has: amount, status)" in text
    assert "TC3 step 1: {{row.amount}} needs a data file" in text
    assert report.has_errors


def test_the_api_rules(make_project):
    _, _, text = findings(make_project({"api/api.yaml": API, "acceptance-criteria.yaml": CRITERIA, "cases/b.yaml": """
        feature: B
        cases:
          - id: TC1
            title: t
            criteria: [AC-1]
            steps:
              - request: {method: DELETE, path: /bookings/X1}
                expect: {status: 204}
              - request: {method: POST, path: /bookings, body: {passenger_name: x}}
                expect: {status: 400}
              - request: {method: GET, path: /health, service: payments}
                expect: {status: 200}
        """}))
    assert "TC1 step 1: DELETE /bookings/X1 is not in api/api.yaml" in text
    assert "TC1 step 2: status 400 is not documented for POST /bookings (documented: 201, 422)" in text
    assert "TC1 step 2: the body leaves out required email" in text
    assert "TC1 step 3: service 'payments' is not in api/api.yaml (it has: bookings)" in text


def test_criteria_steps_and_review_rules(make_project):
    report, keys, text = findings(make_project({"acceptance-criteria.yaml": CRITERIA, "cases/b.yaml": """
        feature: B
        cases:
          - id: TC1
            title: no criterion, checks nothing
            steps:
              - request: {method: GET, path: /bookings}
          - id: TC2
            title: unknown criterion, words only
            criteria: [AC-9]
            manual_steps: [Make a booking]
          - id: TC3
            title: no steps at all
            criteria: [AC-1]
          - id: TC4
            title: approved, then edited
            criteria: [AC-1]
            steps:
              - request: {method: GET, path: /bookings}
                expect: {status: 200}
            review: {status: approved, fingerprint: 000000000000}
        """}))
    assert (WARNING, "TC1", "TC1") in keys and "TC1: linked to no criterion" in text
    assert "TC1 step 1: checks nothing" in text
    assert "TC2: criterion AC-9 is not in acceptance-criteria.yaml" in text
    assert (INFO, "TC2", "TC2") in keys and "TC2: needs steps" in text
    assert (ERROR, "TC3", "TC3") in keys and "TC3: has no steps" in text
    assert "TC4: changed after it was approved" in text
    assert "No api/api.yaml: the rules that need the API are skipped" in text


def test_a_rejected_case_is_left_alone(make_project):
    report, _, _ = findings(make_project({"acceptance-criteria.yaml": CRITERIA, "cases/b.yaml": """
        feature: B
        cases:
          - {id: TC1, title: t, steps: [{request: {method: GET, path: /x}}], review: {status: rejected}}
        """}))
    assert [f for f in report.findings if f.case_id] == []


def test_a_broken_file_and_an_id_in_two_files_are_errors(make_project):
    report, _, text = findings(make_project({"cases/a.yaml": CASES, "cases/b.yaml": CASES,
                                             "cases/c.yaml": "feature: C\ncases:\n  - {id: TC9, title: t, priority: P7}\n"}))
    assert "TC1: the id is also used in cases/a.yaml" in text
    assert "TC9: priority 'P7'" in text
    assert report.has_errors
    assert "No acceptance-criteria.yaml: the criteria rules are skipped" in text


def test_the_report_reads_by_file_with_counts(make_project):
    report, _, _ = findings(make_project({"api/api.yaml": API, "acceptance-criteria.yaml": CRITERIA, "cases/b.yaml": CASES}))
    assert report.as_text().splitlines()[0] == "qa-agent check: t · 1 case in 1 file"
    assert report.as_text().splitlines()[-1] == "No findings."


def _hollow_warnings(make_project, steps: str) -> list[str]:
    report, _, _ = findings(make_project({"api/api.yaml": API, "acceptance-criteria.yaml": CRITERIA, "cases/b.yaml": f"""
        feature: B
        cases:
          - id: TC1
            title: t
            criteria: [AC-1]
            steps: {steps}
        """}))
    return [f.message for f in report.findings if f.level == WARNING and "only status codes" in f.message]


def test_a_case_that_checks_only_status_codes_and_ends_in_success_is_hollow(make_project):
    create = '{request: {method: POST, path: /bookings, body: {passenger_name: "A {{unique}}", email: a@b.c}}, ' \
             'expect: {status: 201}, capture: {pnr: pnr}}'
    read = '{request: {method: GET, path: "/bookings/{{pnr}}"}, expect: {status: 200, max_response_ms: 2000}}'
    warnings = _hollow_warnings(make_project, f"[{create}, {read}]")
    assert len(warnings) == 1 and "Fix: add fields, exists or types" in warnings[0]


def test_a_case_that_ends_in_a_refusal_or_checks_the_response_is_not_hollow(make_project):
    refused = '[{request: {method: POST, path: /bookings, body: {passenger_name: x}}, expect: {status: 422}}]'
    assert _hollow_warnings(make_project, refused) == []
    checked = '[{request: {method: GET, path: /bookings/search}, expect: {status: 200, exists: [bookings]}}]'
    assert _hollow_warnings(make_project, checked) == []
