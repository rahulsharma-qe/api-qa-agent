package apiqa.framework.client;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import apiqa.framework.auth.NoAuth;
import apiqa.framework.auth.TokenProvider;
import apiqa.framework.context.ScenarioContext;
import io.restassured.RestAssured;
import io.restassured.config.HttpClientConfig;
import io.restassured.config.RestAssuredConfig;
import io.restassured.http.ContentType;
import io.restassured.http.Header;
import io.restassured.response.Response;
import io.restassured.specification.RequestSpecification;

/**
 * One service's HTTP calls, on REST Assured. Every request and response is recorded in the scenario
 * context, and the token is masked wherever a request is shown.
 * <pre>
 *   api().post("/bookings", body)              -> ApiResponse
 *   api().withoutAuth().get("/bookings/X")     the same client with no token, for 401 tests
 * </pre>
 */
public final class ApiClient {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final Set<String> SECRET_HEADERS = Set.of("authorization", "x-api-key", "cookie");
    private static final String MASKED = "***";

    private final String baseUrl;
    private final TokenProvider auth;
    private final ScenarioContext context;
    private final RestAssuredConfig config;
    private final double timeoutSeconds;

    public ApiClient(String baseUrl, TokenProvider auth, ScenarioContext context, double timeoutSeconds) {
        this.baseUrl = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        this.auth = auth;
        this.context = context;
        this.timeoutSeconds = timeoutSeconds;
        int milliseconds = (int) (timeoutSeconds * 1000);
        this.config = RestAssuredConfig.config().httpClient(HttpClientConfig.httpClientConfig()
                .setParam("http.connection.timeout", milliseconds)
                .setParam("http.socket.timeout", milliseconds));
    }

    public ApiResponse get(String path) { return request("GET", path, null, Map.of(), Map.of()); }
    public ApiResponse get(String path, Map<String, ?> params) { return request("GET", path, null, params, Map.of()); }
    public ApiResponse get(String path, Map<String, ?> params, Map<String, String> headers) {
        return request("GET", path, null, params, headers);
    }
    public ApiResponse post(String path, Object body) { return request("POST", path, body, Map.of(), Map.of()); }
    public ApiResponse post(String path, Object body, Map<String, String> headers) {
        return request("POST", path, body, Map.of(), headers);
    }
    public ApiResponse put(String path, Object body) { return request("PUT", path, body, Map.of(), Map.of()); }
    public ApiResponse patch(String path, Object body) { return request("PATCH", path, body, Map.of(), Map.of()); }
    public ApiResponse delete(String path) { return request("DELETE", path, null, Map.of(), Map.of()); }

    public ApiClient withoutAuth() {
        return new ApiClient(baseUrl, new NoAuth(), context, timeoutSeconds);
    }

    public ApiResponse request(String method, String path, Object body, Map<String, ?> params, Map<String, String> headers) {
        String url = baseUrl + "/" + path.replaceFirst("^/+", "");
        Map<String, String> allHeaders = new LinkedHashMap<>(auth.headers());
        allHeaders.putAll(headers);

        RequestSpecification request = RestAssured.given().config(config).headers(allHeaders);
        if (!params.isEmpty()) {
            request.queryParams(params);
        }
        if (body != null) {
            request.contentType(ContentType.JSON).body(body);
        }
        long started = System.nanoTime();
        Response raw = request.request(method, url);
        long elapsedMs = (System.nanoTime() - started) / 1_000_000;

        ApiRequest sent = new ApiRequest(method, withQuery(url, params), asJson(body), masked(allHeaders));
        ApiResponse response = new ApiResponse(raw.statusCode(), raw.asString(), headersOf(raw), elapsedMs, sent);
        context.record(response);
        return response;
    }

    private static String withQuery(String url, Map<String, ?> params) {
        if (params.isEmpty()) {
            return url;
        }
        return url + "?" + params.entrySet().stream().map(entry -> entry.getKey() + "=" + entry.getValue())
                .collect(Collectors.joining("&"));
    }

    private static String asJson(Object body) {
        if (body == null) {
            return null;
        }
        try {
            return JSON.writeValueAsString(body);
        } catch (JsonProcessingException error) {
            return String.valueOf(body);
        }
    }

    private static Map<String, String> masked(Map<String, String> headers) {
        Map<String, String> shown = new LinkedHashMap<>();
        headers.forEach((name, value) -> shown.put(name, SECRET_HEADERS.contains(name.toLowerCase()) ? MASKED : value));
        return shown;
    }

    private static Map<String, String> headersOf(Response raw) {
        Map<String, String> headers = new LinkedHashMap<>();
        List<Header> list = raw.getHeaders().asList();
        for (Header header : list) {
            headers.put(header.getName(), header.getValue());
        }
        return headers;
    }
}
