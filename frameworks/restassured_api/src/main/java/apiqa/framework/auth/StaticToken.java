package apiqa.framework.auth;

import java.util.Map;

/** A bearer token given up front (from an environment variable). */
public final class StaticToken implements TokenProvider {
    private final String token;

    public StaticToken(String token) {
        this.token = token;
    }

    @Override
    public Map<String, String> headers() {
        return Map.of("Authorization", "Bearer " + token);
    }
}
