package apiqa.framework.client;

import java.util.Map;
import java.util.Optional;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * What came back from one request, and {@code value()} to read any field by a dotted path:
 * <pre>
 *   response.value("pnr")               a top-level field
 *   response.value("items[0].pnr")      a field inside the first item of a list
 * </pre>
 */
public final class ApiResponse {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final int SHOWN_CHARACTERS = 500;

    private final int statusCode;
    private final String body;
    private final Map<String, String> headers;
    private final long elapsedMs;
    private final ApiRequest request;

    public ApiResponse(int statusCode, String body, Map<String, String> headers, long elapsedMs, ApiRequest request) {
        this.statusCode = statusCode;
        this.body = body == null ? "" : body;
        this.headers = headers;
        this.elapsedMs = elapsedMs;
        this.request = request;
    }

    public int statusCode() { return statusCode; }
    public String body() { return body; }
    public Map<String, String> headers() { return headers; }
    public long elapsedMs() { return elapsedMs; }
    public ApiRequest request() { return request; }

    /** The body as JSON, or null when it isn't JSON (or is empty). */
    public JsonNode json() {
        if (body.isBlank()) {
            return null;
        }
        try {
            return JSON.readTree(body);
        } catch (Exception notJson) {
            return null;
        }
    }

    /** The field's value as a plain Java value (String, Integer, Double, Boolean, List, Map or null). */
    public Object value(String path) {
        JsonNode node = node(path).orElseThrow(() ->
                new FieldNotFound("field '" + path + "' is not in the response\n" + describe()));
        return JSON.convertValue(node, Object.class);
    }

    /** The field's value as text, for carrying into the next step. */
    public String text(String path) {
        return String.valueOf(value(path));
    }

    public boolean has(String path) {
        return node(path).isPresent();
    }

    /** The JSON node at the path, or empty when it isn't there. */
    public Optional<JsonNode> node(String path) {
        JsonNode root = json();
        return root == null ? Optional.empty() : JsonPaths.find(root, path);
    }

    /** Two lines a person can read: the request, then what came back. */
    public String describe() {
        StringBuilder text = new StringBuilder("  ").append(request.method()).append(' ').append(request.url());
        if (request.body() != null && !request.body().isEmpty()) {
            text.append("  ").append(shorten(request.body()));
        }
        return text.append("\n  -> ").append(statusCode).append(' ').append(shorten(body))
                .append("  (").append(elapsedMs).append(" ms)").toString();
    }

    private static String shorten(String text) {
        return text.length() <= SHOWN_CHARACTERS ? text
                : text.substring(0, SHOWN_CHARACTERS) + "... (" + (text.length() - SHOWN_CHARACTERS) + " more characters)";
    }
}
