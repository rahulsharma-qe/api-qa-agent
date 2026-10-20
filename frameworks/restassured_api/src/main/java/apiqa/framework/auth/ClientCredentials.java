package apiqa.framework.auth;

import static io.restassured.RestAssured.given;

import java.util.Map;

import apiqa.framework.config.ConfigException;
import io.restassured.http.ContentType;
import io.restassured.response.Response;

/** Asks the token endpoint once, the first time a header is needed, and reuses the token for the run. */
public final class ClientCredentials implements TokenProvider {
    private final String tokenUrl;
    private final String clientId;
    private final String clientSecret;
    private volatile String token;

    public ClientCredentials(String tokenUrl, String clientId, String clientSecret) {
        this.tokenUrl = tokenUrl;
        this.clientId = clientId;
        this.clientSecret = clientSecret;
    }

    @Override
    public synchronized Map<String, String> headers() {
        if (token == null) {
            Response response = given().contentType(ContentType.JSON)
                    .body(Map.of("client_id", clientId, "client_secret", clientSecret))
                    .post(tokenUrl);
            if (response.statusCode() != 200) {
                throw new ConfigException("token request to " + tokenUrl + " failed: " + response.statusCode() + " "
                        + response.asString());
            }
            token = response.jsonPath().getString("access_token");
        }
        return Map.of("Authorization", "Bearer " + token);
    }
}
