package apiqa.framework;

import static org.testng.Assert.assertEquals;
import static org.testng.Assert.assertFalse;
import static org.testng.Assert.assertNotEquals;
import static org.testng.Assert.assertTrue;
import static org.testng.Assert.expectThrows;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import org.testng.annotations.Test;

import apiqa.framework.client.ApiRequest;
import apiqa.framework.client.ApiResponse;
import apiqa.framework.client.FieldNotFound;
import apiqa.framework.config.ConfigException;
import apiqa.framework.config.EnvironmentConfig;
import apiqa.framework.config.EnvironmentLoader;
import apiqa.framework.context.ScenarioContext;
import apiqa.framework.data.NewPassenger;
import apiqa.framework.data.TestData;
import apiqa.framework.expect.Expect;
import apiqa.framework.expect.ExpectationFailed;

/** The framework's own tests: no service needed. */
public class FrameworkUnitTest {
    private static final String BODY = "{\"pnr\": \"AB12CD\", \"amount\": 250.0, \"refund_allowed\": true, \"count\": 1, "
            + "\"items\": [{\"pnr\": \"AB12CD\", \"status\": \"cancelled\"}], \"nested\": {\"a\": {\"b\": 0}}}";

    private static ApiResponse response(String body, int status) {
        return new ApiResponse(status, body, Map.of("Content-Type", "application/json"), 40,
                new ApiRequest("POST", "http://svc.test/bookings", "{\"amount\":250}", Map.of("Authorization", "***")));
    }

    @Test
    public void valueReadsAnyFieldByPath() {
        ApiResponse response = response(BODY, 200);
        assertEquals(response.value("pnr"), "AB12CD");
        assertEquals(response.value("items[0].status"), "cancelled");
        assertEquals(response.value("nested.a.b"), 0);
        assertTrue(response.has("items[0].pnr"));
        assertFalse(response.has("items[1].pnr"));
    }

    @Test
    public void aMissingPathFailsWithThePathAndTheRequest() {
        FieldNotFound failure = expectThrows(FieldNotFound.class, () -> response(BODY, 200).value("items[3].pnr"));
        assertTrue(failure.getMessage().contains("field 'items[3].pnr' is not in the response"));
        assertTrue(failure.getMessage().contains("POST http://svc.test/bookings"));
    }

    @Test
    public void passingChecksChain() {
        Expect.that(response(BODY, 200)).statusIs(200).fieldEquals("amount", 250).fieldEquals("refund_allowed", true)
                .fieldExists("pnr").fieldIsType("amount", "number").fieldIsType("items", "list").fieldContains("pnr", "AB")
                .listLength("items", 1).listContains("items", "pnr", "AB12CD", "status", "cancelled")
                .listExcludes("items", "pnr", "ZZ0000").headerEquals("content-type", "application/json").respondedWithin(100);
    }

    @Test
    public void eachFailureSaysWhatAndShowsTheRequest() {
        ExpectationFailed status = expectThrows(ExpectationFailed.class, () -> Expect.that(response(BODY, 200)).statusIs(201));
        assertTrue(status.getMessage().startsWith("expected status 201, got 200"));
        assertTrue(status.getMessage().contains("POST http://svc.test/bookings  {\"amount\":250}"));
        ExpectationFailed notTrue = expectThrows(ExpectationFailed.class,
                () -> Expect.that(response(BODY, 200)).fieldEquals("count", true));      // 1 is not true
        assertTrue(notTrue.getMessage().startsWith("field 'count': expected true, got 1"));
        ExpectationFailed type = expectThrows(ExpectationFailed.class,
                () -> Expect.that(response(BODY, 200)).fieldIsType("refund_allowed", "integer"));
        assertTrue(type.getMessage().startsWith("field 'refund_allowed': expected an integer"));
    }

    @Test
    public void contextRemembersValuesAndNamesWhatIsKnown() {
        ScenarioContext context = new ScenarioContext();
        assertEquals(context.remember("pnr", "AB12CD"), "AB12CD");
        IllegalStateException missing = expectThrows(IllegalStateException.class, () -> context.get("token"));
        assertTrue(missing.getMessage().contains("'token' was never remembered (remembered: pnr)"));
        context.record(response(BODY, 201));
        assertTrue(context.history().startsWith("step 1\n  POST http://svc.test/bookings"));
    }

    @Test
    public void csvAndExcelGiveTheSameTypedRows() {
        List<Map<String, Object>> csv = TestData.rows("data/cancellation_boundaries.csv");
        List<Map<String, Object>> excel = TestData.rows("data/cancellation_boundaries.xlsx");
        assertEquals(excel, csv);
        assertEquals(csv.get(1).get("refund_allowed"), true);
        assertEquals(csv.get(1).get("expected_status"), 200);
        assertEquals(csv.get(3).get("refund_amount"), null);
    }

    @Test
    public void uniqueIdsAreSixCharactersAndNew() {
        String first = TestData.uniqueId();
        assertTrue(first.matches("[0-9a-f]{6}"), first);
        assertNotEquals(TestData.uniqueId(), first);
    }

    @Test
    public void newPassengersNeverClash() {
        Map<String, Object> first = NewPassenger.create();
        assertNotEquals(first, NewPassenger.create());
        assertTrue(String.valueOf(first.get("email")).endsWith("@testdata.example"));
        assertEquals(NewPassenger.with("amount", 250).get("amount"), 250);
    }

    @Test
    public void environmentsAreReadFromTheSharedFile() {
        EnvironmentConfig demo = EnvironmentLoader.load(Path.of("config/environments.yaml"), "demo");
        assertEquals(demo.baseUrl(), "http://localhost:8000");
        assertEquals(demo.baseUrl("notifications"), "http://localhost:8001");
        assertTrue(EnvironmentLoader.load(Path.of("config/environments.yaml"), "staging").readOnly());
        ConfigException unknown = expectThrows(ConfigException.class,
                () -> EnvironmentLoader.load(Path.of("config/environments.yaml"), "qa9"));
        assertTrue(unknown.getMessage().contains("unknown environment 'qa9'"));
        ConfigException service = expectThrows(ConfigException.class, () -> demo.baseUrl("payments"));
        assertTrue(service.getMessage().contains("no service 'payments'"));
    }
}
