package apiqa.examples;

import org.testng.annotations.Test;

import apiqa.framework.expect.Expect;
import apiqa.framework.testng.BaseTest;
import apiqa.framework.testng.CaseId;
import apiqa.framework.testng.Priority;

/** apiFor("<service>"): the same environment, another service, the same report. */
public class OtherServicesTest extends BaseTest {

    @Test(groups = {"smoke", "regression"})
    @CaseId("EX-SVC-01") @Priority("P0")
    public void eachServiceAnswersItsHealthCheck() {
        for (String service : new String[] {"bookings", "notifications"}) {
            Expect.that(apiFor(service).get("/health-check")).statusIs(200).fieldEquals("service", service)
                    .respondedWithin(2000);
        }
    }
}
