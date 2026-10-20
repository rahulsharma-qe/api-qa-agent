package apiqa.examples;

import org.testng.annotations.Test;

import apiqa.framework.client.ApiResponse;
import apiqa.framework.data.NewPassenger;
import apiqa.framework.expect.Expect;
import apiqa.framework.testng.BaseTest;
import apiqa.framework.testng.CaseId;
import apiqa.framework.testng.Priority;

/** GET: a booking that exists, one that doesn't, and a call without a token. */
public class GetBookingTest extends BaseTest {

    @Test(groups = {"smoke", "regression", "writes"})
    @CaseId("EX-GET-01") @Priority("P0")
    public void getReturnsTheBookingThatWasMade() {
        ApiResponse created = api().post("/bookings", NewPassenger.with("amount", 120));
        Expect.that(created).statusIs(201);
        String pnr = context().remember("pnr", created.text("pnr"));

        Expect.that(api().get("/bookings/" + pnr)).statusIs(200).fieldEquals("pnr", pnr)
                .fieldEquals("status", "active").fieldEquals("amount", 120).fieldIsType("booked_at", "string");
    }

    @Test(groups = "regression")
    @CaseId("EX-GET-02") @Priority("P1")
    public void anUnknownPnrIs404() {
        Expect.that(api().get("/bookings/NOPE00")).statusIs(404).fieldEquals("error.code", "booking_not_found");
    }

    @Test(groups = "regression")
    @CaseId("EX-GET-03") @Priority("P1")
    public void withoutATokenTheAnswerIs401() {
        Expect.that(api().withoutAuth().get("/bookings/NOPE00")).statusIs(401).fieldEquals("error.code", "unauthorized");
    }
}
