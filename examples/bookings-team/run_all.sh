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
# 2. Start the reference API (unless it is already up), check the environment, run the tests.
# 3. Trace: criteria -> cases -> tests -> results, with coverage; fail if an approved case has no test.
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
qa-agent review import
qa-agent generate
for folder in api cases data tests/generated src/test/java/generated; do
  diff -r "$folder" "$example/$folder" -x __pycache__
done
echo "Same as committed."

echo "== 2. The reference API, the environment, the tests"
cd "$example"
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
