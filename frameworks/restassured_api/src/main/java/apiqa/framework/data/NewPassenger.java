package apiqa.framework.data;

import java.security.SecureRandom;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;

/** A passenger no other test is using: a unique name and a test-only email address. */
public final class NewPassenger {
    public static final String TEST_EMAIL_DOMAIN = "testdata.example";
    private static final SecureRandom RANDOM = new SecureRandom();

    private NewPassenger() {
    }

    public static Map<String, Object> create() {
        byte[] bytes = new byte[3];
        RANDOM.nextBytes(bytes);
        String tag = HexFormat.of().formatHex(bytes);
        Map<String, Object> passenger = new LinkedHashMap<>();
        passenger.put("passenger_name", "Test Passenger " + tag);
        passenger.put("email", "passenger-" + tag + "@" + TEST_EMAIL_DOMAIN);
        return passenger;
    }

    /** A new passenger plus more fields: NewPassenger.with("amount", 250, "booked_at", "2026-01-15T10:00:00Z"). */
    public static Map<String, Object> with(Object... fieldsAndValues) {
        if (fieldsAndValues.length % 2 != 0) {
            throw new IllegalArgumentException("give fields and values in pairs: \"amount\", 250");
        }
        Map<String, Object> body = create();
        for (int i = 0; i < fieldsAndValues.length; i += 2) {
            body.put(String.valueOf(fieldsAndValues[i]), fieldsAndValues[i + 1]);
        }
        return body;
    }
}
