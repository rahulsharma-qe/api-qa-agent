package apiqa.examples;

import java.util.Map;

import org.testng.SkipException;
import org.testng.annotations.Test;

import apiqa.framework.client.ApiClient;
import apiqa.framework.client.ApiResponse;
import apiqa.framework.data.NewPassenger;
import apiqa.framework.expect.Expect;
import apiqa.framework.testng.BaseTest;
import apiqa.framework.testng.CaseId;
import apiqa.framework.testng.Priority;

/**
 * A chain across four endpoints: ask for a token, make a booking with it, cancel it, read the refund.
 * The other examples get their token from the environment automatically; this one carries it by hand.
 */
public class AuthChainTest extends BaseTest {

    @Test(groups = {"regression", "writes"})
    @CaseId("EX-CHAIN-01") @Priority("P1")
    public void tokenThenBookingThenCancelThenRefundStatus() {
        Map<String, Object> auth = environment().auth();
        if (!auth.containsKey("client_id")) {
            throw new SkipException("this example reads plain credentials, which only the demo environment has");
        }
        ApiClient anonymous = api().withoutAuth();

        ApiResponse token = anonymous.post("/auth/token",
                Map.of("client_id", auth.get("client_id"), "client_secret", auth.get("client_secret")));
        Expect.that(token).statusIs(200).fieldEquals("token_type", "Bearer");
        Map<String, String> bearer = Map.of("Authorization", "Bearer " + context().remember("token", token.text("access_token")));

        ApiResponse created = anonymous.post("/bookings",
                NewPassenger.with("amount", 300, "booked_at", "2026-01-15T10:00:00Z"), bearer);
        Expect.that(created).statusIs(201);
        String pnr = context().remember("pnr", created.text("pnr"));

        ApiResponse cancelled = anonymous.post("/bookings/" + pnr + "/cancel", Map.of("cancelled_at", "2026-01-15T18:00:00Z"), bearer);
        Expect.that(cancelled).statusIs(200).fieldEquals("refund_allowed", true);

        Expect.that(anonymous.get("/bookings/" + pnr + "/refund", Map.of(), bearer)).statusIs(200)
                .fieldEquals("refund_status", "refunded").fieldEquals("refund_amount", 300);
    }
}
