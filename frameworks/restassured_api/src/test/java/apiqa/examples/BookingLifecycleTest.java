package apiqa.examples;

import java.util.Map;

import org.testng.annotations.Test;

import apiqa.framework.client.ApiResponse;
import apiqa.framework.data.NewPassenger;
import apiqa.framework.expect.Expect;
import apiqa.framework.testng.BaseTest;
import apiqa.framework.testng.CaseId;
import apiqa.framework.testng.Priority;

/** Create, read, update, read, delete, read: one booking's whole life, its PNR carried step to step. */
public class BookingLifecycleTest extends BaseTest {

    @Test(groups = {"regression", "writes"})
    @CaseId("EX-CRUD-01") @Priority("P1")
    public void aBookingFromCreationToDeletion() {
        Map<String, Object> passenger = NewPassenger.with("amount", 250);
        ApiResponse created = api().post("/bookings", passenger);
        Expect.that(created).statusIs(201).fieldEquals("status", "active");
        String pnr = context().remember("pnr", created.text("pnr"));

        Expect.that(api().get("/bookings/" + pnr)).statusIs(200).fieldEquals("passenger_name", passenger.get("passenger_name"));

        Map<String, Object> renamed = NewPassenger.create();
        renamed.put("passenger_name", "Asha Rao");
        Expect.that(api().put("/bookings/" + pnr, renamed)).statusIs(200);
        Expect.that(api().get("/bookings/" + pnr)).statusIs(200).fieldEquals("passenger_name", "Asha Rao")
                .fieldEquals("email", renamed.get("email")).fieldEquals("amount", 250);

        Expect.that(api().delete("/bookings/" + pnr)).statusIs(204);
        Expect.that(api().get("/bookings/" + pnr)).statusIs(404);
    }

    @Test(groups = {"regression", "writes"})
    @CaseId("EX-CRUD-02") @Priority("P2")
    public void theAmountCannotBeChanged() {
        String pnr = context().remember("pnr", api().post("/bookings", NewPassenger.with("amount", 250)).text("pnr"));
        ApiResponse refused = api().put("/bookings/" + pnr, NewPassenger.with("amount", 1));
        Expect.that(refused).statusIs(422).fieldContains("error.message", "amount cannot be changed");
        Expect.that(api().get("/bookings/" + pnr)).fieldEquals("amount", 250);
    }
}
