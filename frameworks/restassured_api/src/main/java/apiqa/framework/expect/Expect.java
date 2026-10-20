package apiqa.framework.expect;

import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import apiqa.framework.client.ApiResponse;

/**
 * Checks on a response, chained. Each failure says what was expected, what came back, and the request
 * that produced it:
 * <pre>
 *   Expect.that(response).statusIs(200).fieldEquals("refund_allowed", true).fieldEquals("refund_amount", 250);
 * </pre>
 */
public final class Expect {
    private static final ObjectMapper JSON = new ObjectMapper();
    private final ApiResponse response;

    private Expect(ApiResponse response) {
        this.response = response;
    }

    public static Expect that(ApiResponse response) {
        return new Expect(response);
    }

    public Expect statusIs(int expected) {
        if (response.statusCode() != expected) {
            fail("expected status " + expected + ", got " + response.statusCode());
        }
        return this;
    }

    public Expect fieldEquals(String path, Object expected) {
        Object actual = value(path);
        if (!same(actual, expected)) {
            fail("field '" + path + "': expected " + show(expected) + ", got " + show(actual));
        }
        return this;
    }

    public Expect fieldExists(String path) {
        node(path);
        return this;
    }

    /** type: string, number, integer, boolean, list, object or null. */
    public Expect fieldIsType(String path, String type) {
        JsonNode node = node(path);
        boolean matches;
        switch (type) {
            case "string": matches = node.isTextual(); break;
            case "number": matches = node.isNumber(); break;
            case "integer": matches = node.isIntegralNumber(); break;
            case "boolean": matches = node.isBoolean(); break;
            case "list": matches = node.isArray(); break;
            case "object": matches = node.isObject(); break;
            case "null": matches = node.isNull(); break;
            default: throw new IllegalArgumentException("unknown type '" + type
                    + "' (use string, number, integer, boolean, list, object or null)");
        }
        if (!matches) {
            String article = "aeiou".indexOf(type.charAt(0)) >= 0 ? "an" : "a";
            fail("field '" + path + "': expected " + article + " " + type + ", got " + node.getNodeType().name().toLowerCase()
                    + " " + node);
        }
        return this;
    }

    public Expect fieldContains(String path, String text) {
        Object actual = value(path);
        if (!String.valueOf(actual).contains(text)) {
            fail("field '" + path + "': expected it to contain '" + text + "', got " + show(actual));
        }
        return this;
    }

    public Expect listLength(String path, int expected) {
        JsonNode node = node(path);
        if (!node.isArray() || node.size() != expected) {
            fail("field '" + path + "': expected " + expected + " item(s), got "
                    + (node.isArray() ? String.valueOf(node.size()) : "not a list"));
        }
        return this;
    }

    /** At least one item in the list has every given field: listContains("items", "pnr", pnr, "status", "cancelled"). */
    public Expect listContains(String path, Object... fieldsAndValues) {
        Map<String, Object> match = pairs(fieldsAndValues);
        if (!anyItemMatches(path, match)) {
            fail("field '" + path + "': no item with " + match);
        }
        return this;
    }

    /** No item in the list has every given field. */
    public Expect listExcludes(String path, Object... fieldsAndValues) {
        Map<String, Object> match = pairs(fieldsAndValues);
        if (anyItemMatches(path, match)) {
            fail("field '" + path + "': expected no item with " + match + ", found one");
        }
        return this;
    }

    public Expect headerEquals(String name, String expected) {
        String actual = response.headers().entrySet().stream()
                .filter(header -> header.getKey().equalsIgnoreCase(name))
                .map(Map.Entry::getValue).findFirst().orElse(null);
        if (!Objects.equals(actual, expected)) {
            fail("header '" + name + "': expected '" + expected + "', got " + (actual == null ? "none" : "'" + actual + "'"));
        }
        return this;
    }

    public Expect respondedWithin(long milliseconds) {
        if (response.elapsedMs() > milliseconds) {
            fail("expected an answer within " + milliseconds + " ms, took " + response.elapsedMs() + " ms");
        }
        return this;
    }

    private boolean anyItemMatches(String path, Map<String, Object> match) {
        JsonNode list = node(path);
        if (!list.isArray()) {
            fail("field '" + path + "': expected a list");
        }
        for (JsonNode item : list) {
            if (!item.isObject()) {
                continue;
            }
            boolean all = true;
            for (Map.Entry<String, Object> wanted : match.entrySet()) {
                Object actual = item.has(wanted.getKey()) ? JSON.convertValue(item.get(wanted.getKey()), Object.class) : null;
                all &= item.has(wanted.getKey()) && same(actual, wanted.getValue());
            }
            if (all) {
                return true;
            }
        }
        return false;
    }

    private JsonNode node(String path) {
        return response.node(path).orElseThrow(() ->
                new ExpectationFailed("field '" + path + "' is not in the response\n" + response.describe()));
    }

    private Object value(String path) {
        return JSON.convertValue(node(path), Object.class);
    }

    private void fail(String message) {
        throw new ExpectationFailed(message + "\n" + response.describe());
    }

    /** Equal, treating 250 and 250.0 as the same number but never true as 1. */
    static boolean same(Object actual, Object expected) {
        if (actual instanceof Boolean || expected instanceof Boolean) {
            return Objects.equals(actual, expected);
        }
        if (actual instanceof Number && expected instanceof Number) {
            return new BigDecimal(actual.toString()).compareTo(new BigDecimal(expected.toString())) == 0;
        }
        return Objects.equals(actual, expected);
    }

    private static String show(Object value) {
        return value instanceof String ? "'" + value + "'" : String.valueOf(value);
    }

    private static Map<String, Object> pairs(Object... fieldsAndValues) {
        if (fieldsAndValues.length % 2 != 0) {
            throw new IllegalArgumentException("give fields and values in pairs: \"pnr\", pnr, \"status\", \"cancelled\"");
        }
        Map<String, Object> match = new LinkedHashMap<>();
        for (int i = 0; i < fieldsAndValues.length; i += 2) {
            match.put(String.valueOf(fieldsAndValues[i]), fieldsAndValues[i + 1]);
        }
        return match;
    }
}
