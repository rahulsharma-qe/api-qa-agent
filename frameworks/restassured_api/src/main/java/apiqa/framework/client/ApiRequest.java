package apiqa.framework.client;

import java.util.Map;

/** What was sent. The Authorization value is already masked. */
public record ApiRequest(String method, String url, String body, Map<String, String> headers) {
}
