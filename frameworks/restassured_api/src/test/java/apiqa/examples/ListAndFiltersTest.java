package apiqa.examples;

import java.util.Map;

import org.testng.annotations.Test;

import apiqa.framework.data.NewPassenger;
import apiqa.framework.expect.Expect;
import apiqa.framework.testng.BaseTest;
import apiqa.framework.testng.CaseId;
import apiqa.framework.testng.Priority;

/** Lists check the test's own items, never totals: other tests (or teams) may be using the service. */
public class ListAndFiltersTest extends BaseTest {

    @Test(groups = {"functional", "writes"})
    @CaseId("EX-LIST-01") @Priority("P2")
    public void theStatusFilter() {
        String active = api().post("/bookings", NewPassenger.with("amount", 10)).text("pnr");
        String cancelled = api().post("/bookings", NewPassenger.with("amount", 20, "booked_at", "2026-01-15T10:00:00Z")).text("pnr");
        api().post("/bookings/" + cancelled + "/cancel", Map.of("cancelled_at", "2026-01-15T11:00:00Z"));

        Expect.that(api().get("/bookings", Map.of("status", "cancelled", "limit", 100))).statusIs(200)
                .fieldIsType("items", "list")
                .listContains("items", "pnr", cancelled, "status", "cancelled")
                .listExcludes("items", "pnr", active);
    }

    @Test(groups = "functional")
    @CaseId("EX-LIST-02") @Priority("P3")
    public void limitAndABadFilter() {
        Expect.that(api().get("/bookings", Map.of("limit", 1))).statusIs(200).fieldIsType("count", "integer");
        Expect.that(api().get("/bookings", Map.of("status", "unknown"))).statusIs(422).fieldEquals("error.code", "invalid_request");
    }
}
