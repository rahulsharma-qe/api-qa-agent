package apiqa.framework.auth;

import java.util.Map;

/** No Authorization header. */
public final class NoAuth implements TokenProvider {
    @Override
    public Map<String, String> headers() {
        return Map.of();
    }
}
