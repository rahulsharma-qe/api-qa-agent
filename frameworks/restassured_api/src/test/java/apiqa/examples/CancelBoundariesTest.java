package apiqa.examples;

import java.util.Map;

import org.testng.annotations.DataProvider;
import org.testng.annotations.Test;

import apiqa.framework.client.ApiResponse;
import apiqa.framework.data.NewPassenger;
import apiqa.framework.data.TestData;
import apiqa.framework.expect.Expect;
import apiqa.framework.testng.BaseTest;
import apiqa.framework.testng.CaseId;
import apiqa.framework.testng.Priority;

/** Data-driven from Excel: the 24-hour refund boundary, one run per row of data/cancellation_boundaries.xlsx. */
public class CancelBoundariesTest extends BaseTest {

    @DataProvider(name = "boundaries")
    public Object[][] boundaries() {
        return TestData.asDataProvider(TestData.rows("data/cancellation_boundaries.xlsx"));
    }

    @Test(groups = {"regression", "writes"}, dataProvider = "boundaries")
    @CaseId("EX-REFUND-01") @Priority("P0")
    public void refundAtThe24HourBoundary(Map<String, Object> row) {
        ApiResponse created = api().post("/bookings", NewPassenger.with("amount", 250, "booked_at", row.get("booked_at")));
        String pnr = context().remember("pnr", created.text("pnr"));

        ApiResponse cancelled = api().post("/bookings/" + pnr + "/cancel", Map.of("cancelled_at", row.get("cancelled_at")));
        int expectedStatus = ((Number) row.get("expected_status")).intValue();
        Expect expect = Expect.that(cancelled).statusIs(expectedStatus);
        if (expectedStatus == 200) {
            expect.fieldEquals("refund_allowed", row.get("refund_allowed")).fieldEquals("refund_amount", row.get("refund_amount"));
        }
    }

    @Test(groups = {"regression", "writes"})
    @CaseId("EX-REFUND-02") @Priority("P1")
    public void aSecondCancelIsRefusedAndChangesNothing() {
        String pnr = context().remember("pnr",
                api().post("/bookings", NewPassenger.with("amount", 250, "booked_at", "2026-01-15T10:00:00Z")).text("pnr"));
        Expect.that(api().post("/bookings/" + pnr + "/cancel", Map.of("cancelled_at", "2026-01-15T11:00:00Z"))).statusIs(200);
        Expect.that(api().post("/bookings/" + pnr + "/cancel", Map.of("cancelled_at", "2026-01-20T11:00:00Z")))
                .statusIs(409).fieldEquals("error.code", "already_cancelled");
        Expect.that(api().get("/bookings/" + pnr + "/refund")).fieldEquals("refund_status", "refunded");
    }
}
