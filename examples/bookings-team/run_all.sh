#!/usr/bin/env bash
# Every qa-agent step on this example, from its inputs, then both frameworks' tests and the trace.
# CI runs it; so can you, after pip install -e . -e frameworks/python_api at the repository's root.
#
#   ./run_all.sh                 both frameworks (the REST Assured framework installed once:
#                                cd frameworks/restassured_api && ./mvnw -q install -DskipTests)
#   ./run_all.sh --pytest-only   no Java needed
#
# 1. In a scratch copy: import the API and the team's existing cases again, apply the filled review
#    sheet, generate; everything must come out exactly as committed.
# 2. The drift check; start the reference API (unless it is already up); the environment; the tests;
#    what each suite and priority picks (pytest -m regression, sanity, p0; -Dgroups=p0).
# 3. Trace: criteria -> cases -> tests -> results, with coverage; fail if an approved case has no test.
# 4. Promote: the Python tests twice more, then the cases stable enough for regression (listed only).
# 5. The bug-detection rate: the Python tests once per seeded bug in the reference API.
set -euo pipefail
cd "$(dirname "$0")"
example="$(pwd)"
frameworks="pytest restassured"
[[ "${1:-}" == "--pytest-only" ]] && frameworks="pytest"

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
if ! python -m env_check --env demo > /dev/null 2>&1; then
  python -m demo_api > reports/demo_api.log 2>&1 &
  demo=$!
  trap 'rm -rf "$scratch"; kill "$demo" 2> /dev/null || true' EXIT
fi
python -m env_check --env demo
results=()
if [[ " $frameworks " == *" pytest "* ]]; then
  python -m pytest -q --junitxml=reports/junit.xml
  results+=(reports/junit.xml)
  for pick in regression sanity p0; do
    printf '  pytest -m %-11s %s\n' "$pick" "$( (python -m pytest -q --collect-only -m "$pick" || true) | tail -1)"
  done
fi
if [[ " $frameworks " == *" restassured "* ]]; then
  rm -rf target/surefire-reports
  ./mvnw -q -B test -Dgroups=p0                      # by priority: @Priority("P0") is the group p0
  p0_tests="$(cat target/surefire-reports/TEST-*.xml | grep -c "<testcase" || true)"
  echo "  ./mvnw test -Dgroups=p0   $p0_tests tests"
  [[ "$p0_tests" -gt 0 ]]
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
if [[ -n "${demo:-}" ]]; then
  kill "$demo"
  wait "$demo" 2> /dev/null || true
  qa-agent bug-detection --framework pytest
else
  echo "The reference API was already running: stop it, then run qa-agent bug-detection --framework pytest"
fi
