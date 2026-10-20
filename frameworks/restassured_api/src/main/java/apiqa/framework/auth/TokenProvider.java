package apiqa.framework.auth;

import java.util.Map;

/** Where the Authorization header comes from. */
public interface TokenProvider {
    Map<String, String> headers();
}
