#!/usr/bin/env bash
# Every qa-agent step on this example, from its inputs, then both stacks' tests and the trace.
# CI runs it; so can you, after pip install -e . -e frameworks/python_api at the repository's root.
#
#   ./run_all.sh                 both stacks (the REST Assured framework installed once:
#                                cd frameworks/restassured_api && ./mvnw -q install -DskipTests)
#   ./run_all.sh --python-only   no Java needed
#
# 1. In a scratch copy: import the API and the team's existing cases again, apply the filled review
#    sheet, generate; everything must come out exactly as committed.
# 2. The drift check; start the reference API (unless it is already up); the environment; the tests.
# 3. Trace: criteria -> cases -> tests -> results, with coverage; fail if an approved case has no test.
# 4. Promote: the Python tests twice more, then the cases stable enough for regression (listed only).
# 5. The bug-detection rate: the Python tests once per seeded bug in the reference API.
set -euo pipefail
cd "$(dirname "$0")"
example="$(pwd)"
stacks="python restassured"
[[ "${1:-}" == "--python-only" ]] && stacks="python"

echo "== 1. Rebuild from the inputs, in a scratch copy, and compare"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
cp -r "$example" "$scratch/bookings-team"
cd "$scratch/bookings-team"
rm -f cases/bookings-api.yaml cases/refunds.yaml cases/bookings-smoke.yaml cases/cancellation-scenarios.yaml \
      data/cancellation-scenarios-tc040.csv
rm -rf tests/generated src/test/java/generated
qa-agent import api api/source/openapi.json api/source/cancel_booking.curl
qa-agent import api api/source/notifications_health.curl --service notifications
qa-agent import cases existing/*
qa-agent check
qa-agent review apply
qa-agent generate
for folder in api cases data tests/generated src/test/java/generated; do
  diff -r "$folder" "$example/$folder" -x __pycache__
done
echo "Same as committed."

echo "== 2. The drift check, the reference API, the environment, the tests"
cd "$example"
qa-agent generate --check
mkdir -p reports
if ! python -m env_check --env mock > /dev/null 2>&1; then
  python -m mock_service > reports/mock_service.log 2>&1 &
  mock=$!
  trap 'rm -rf "$scratch"; kill "$mock" 2> /dev/null || true' EXIT
fi
python -m env_check --env mock
results=()
if [[ " $stacks " == *" python "* ]]; then
  python -m pytest -q --junitxml=reports/junit.xml
  results+=(reports/junit.xml)
fi
if [[ " $stacks " == *" restassured "* ]]; then
  ./mvnw -q -B test
  results+=(target/surefire-reports)
fi

echo "== 3. Trace"
qa-agent trace --results "${results[@]}" --check

echo "== 4. Promote (listed only: a person applies it with --apply)"
cp reports/junit.xml reports/run1.xml
for run in 2 3; do
  python -m pytest -q --junitxml="reports/run$run.xml" > /dev/null
done
qa-agent promote --runs reports/run1.xml reports/run2.xml reports/run3.xml

echo "== 5. Bug-detection rate (seeded bugs, one at a time)"
if [[ -n "${mock:-}" ]]; then
  kill "$mock"
  wait "$mock" 2> /dev/null || true
  qa-agent bug-detection --stack python
else
  echo "The reference API was already running: stop it, then run qa-agent bug-detection --stack python"
fi
