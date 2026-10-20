"""api_for("<service>"): the same environment, another service, the same report."""

import pytest

from api_test_framework import Expect


@pytest.mark.regression
@pytest.mark.smoke
@pytest.mark.case("EX-SVC-01")
@pytest.mark.priority("P0")
def test_each_service_answers_its_health_check(api_for):
    for service in ("bookings", "notifications"):
        Expect(api_for(service).get("/health-check")).status_is(200).field_equals("service", service) \
            .responded_within(2000)
