"""The command line: import api, check, and the exit codes."""

import json

from qa_agent.cli import main

from tests.qa_agent.conftest import CRITERIA

OPENAPI = {"openapi": "3.0.3", "info": {"title": "t", "version": "1"},
           "paths": {"/bookings": {"post": {"responses": {"201": {}}}}}}


def test_import_api_writes_the_model_and_merges_a_second_source(make_project, capsys):
    root = make_project({"api/source/openapi.json": json.dumps(OPENAPI),
                         "api/source/get.curl": "curl https://h/bookings/AB12CD\n### response\n200\n"})
    assert main(["--project", str(root), "import", "api", str(root / "api/source/openapi.json")]) == 0
    assert main(["--project", str(root), "import", "api", str(root / "api/source/get.curl")]) == 0
    model = (root / "api/api.yaml").read_text()
    assert "path: /bookings\n" in model and "path: /bookings/{id}" in model
    assert "read AB12CD -> {id}" in capsys.readouterr().out


def test_check_exits_0_without_errors_and_1_with_them(make_project, capsys):
    good = make_project({"criteria.yaml": CRITERIA, "cases/a.yaml": """
        feature: A
        cases:
          - {id: TC1, title: t, criteria: [AC-1], steps: [{request: {method: GET, path: /x}, expect: {status: 200}}]}
        """})
    assert main(["--project", str(good), "check"]) == 0
    (good / "cases/a.yaml").write_text("feature: A\ncases:\n  - {id: TC1, title: t, criteria: [AC-7], manual_steps: [x]}\n")
    assert main(["--project", str(good), "check"]) == 1
    assert "criterion AC-7 is not in criteria.yaml" in capsys.readouterr().out


def test_a_folder_that_is_not_a_project_is_a_setup_problem(tmp_path, capsys):
    assert main(["--project", str(tmp_path), "check"]) == 2
    assert "no qa-agent.yaml" in capsys.readouterr().err


def test_a_bad_project_file_is_a_setup_problem(make_project, capsys):
    root = make_project({}, config="team: t\nframeworks: [cobol]\n")
    assert main(["--project", str(root), "check"]) == 2
    err = capsys.readouterr().err
    assert "'service' is missing" in err and "unknown framework 'cobol'" in err


def test_a_missing_api_file_is_a_setup_problem(make_project, capsys):
    root = make_project({})
    assert main(["--project", str(root), "import", "api", str(root / "openapi.json")]) == 2
    assert "no such file" in capsys.readouterr().err


def test_no_command_shows_the_help(capsys):
    assert main([]) == 2
    assert "import" in capsys.readouterr().out
