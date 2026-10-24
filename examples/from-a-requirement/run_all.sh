#!/usr/bin/env bash
# From a requirement in plain words to tests that run, with a person approving every AI step.
# The model's replies are recorded in ai/recorded/ (hand-written: see the README there), so this
# needs no API key and prints the same every time. CI runs it; so can you, after
#   pip install -e . -e frameworks/python_api      (at the repository's root)
#
# 1-8. In a scratch copy, from the team's inputs only (the requirement, the API, the filled review
#      sheets): criteria, review, cases, review, a redo, review, a requirement change, generate.
#      Everything must come out exactly as committed.
# 9.   The tests, against the reference API, and the trace.
set -euo pipefail
cd "$(dirname "$0")"
example="$(pwd)"

# A step that finds problems exits 1 (a reply refused, a check error): here that is expected,
# and shown. Any other exit stops the run.
expect_exit() {
  local wanted=$1; shift
  set +e; "$@"; local got=$?; set -e
  if [[ $got -ne $wanted ]]; then echo "expected exit $wanted, got $got: $*"; exit 1; fi
}

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
cp -r "$example" "$scratch/team"
cd "$scratch/team"
rm -rf acceptance-criteria-drafts.yaml cases tests/generated reports

echo "== 1. Criteria and questions from the requirement, pasted in and named by its ticket"
expect_exit 1 qa-agent draft criteria - --ref BOOK-101 < requirements/BOOK-101.md

echo "== 2. A person approves the criteria and answers the questions (review/1-criteria.xlsx)"
qa-agent review apply --sheet review/1-criteria.xlsx

echo "== 3. A draft case for each gap: the plan first, then the drafts"
qa-agent draft cases --plan
expect_exit 1 qa-agent draft cases

echo "== 4. check, then a person decides on each draft (review/2-cases.xlsx)"
expect_exit 1 qa-agent check
qa-agent review apply --sheet review/2-cases.xlsx

echo "== 5. The case sent back is redone, with the reviewer's comment; asked again, nothing happens"
qa-agent draft cases --redo TC005
expect_exit 1 qa-agent draft cases --redo TC005

echo "== 6. A person approves the redone case (review/3-redo.xlsx)"
qa-agent review apply --sheet review/3-redo.xlsx

echo "== 7. The requirement changed (24 hours became 48): what changes, before any call"
qa-agent draft criteria - --ref BOOK-101 --plan < requirements/BOOK-101-v2.md

echo "== 8. The approved cases become tests"
qa-agent generate
for item in acceptance-criteria-drafts.yaml cases tests/generated; do
  diff -r "$item" "$example/$item" -x __pycache__
done
echo "Same as committed."

echo "== 9. The tests, against the reference API, and the trace"
cd "$example"
qa-agent generate --check
mkdir -p reports
if ! python -m env_check --env demo > /dev/null 2>&1; then
  python -m demo_api > reports/demo_api.log 2>&1 &
  demo=$!
  trap 'rm -rf "$scratch"; kill "$demo" 2> /dev/null || true' EXIT
fi
python -m env_check --env demo
python -m pytest -q --junitxml=reports/junit.xml
qa-agent trace --results reports/junit.xml --check
