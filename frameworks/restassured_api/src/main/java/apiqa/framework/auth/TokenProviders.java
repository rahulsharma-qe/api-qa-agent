package apiqa.framework.auth;

import java.util.Map;

import apiqa.framework.config.ConfigException;
import apiqa.framework.config.EnvironmentConfig;

/**
 * Chooses a token provider from the environment's {@code auth.type}:
 * {@code none}, {@code static_token} (token_env) or {@code client_credentials}
 * (service, token_path, client_id_env, client_secret_env; plain client_id / client_secret for a mock only).
 */
public final class TokenProviders {
    private TokenProviders() {
    }

    public static TokenProvider forEnvironment(EnvironmentConfig environment) {
        Map<String, Object> auth = environment.auth();
        String type = String.valueOf(auth.getOrDefault("type", "none"));
        switch (type) {
            case "none":
                return new NoAuth();
            case "static_token":
                return new StaticToken(secret(auth, "token", environment.name()));
            case "client_credentials": {
                String service = auth.containsKey("service") ? String.valueOf(auth.get("service")) : environment.defaultService();
                String path = String.valueOf(auth.getOrDefault("token_path", "/auth/token"));
                String tokenUrl = environment.baseUrl(service) + "/" + path.replaceFirst("^/+", "");
                return new ClientCredentials(tokenUrl, secret(auth, "client_id", environment.name()),
                        secret(auth, "client_secret", environment.name()));
            }
            default:
                throw new ConfigException("environment '" + environment.name() + "': unknown auth type '" + type
                        + "' (use none, static_token or client_credentials)");
        }
    }

    /** A value from {@code <name>_env} (an environment variable), or a plain {@code <name>} (a mock only). */
    private static String secret(Map<String, Object> auth, String name, String environment) {
        Object variable = auth.get(name + "_env");
        if (variable != null) {
            String value = System.getenv(String.valueOf(variable));
            if (value == null || value.isBlank()) {
                throw new ConfigException("environment '" + environment + "' needs the environment variable " + variable);
            }
            return value;
        }
        if (auth.containsKey(name)) {
            return String.valueOf(auth.get(name));
        }
        throw new ConfigException("environment '" + environment + "': auth needs '" + name + "_env' (or '" + name + "' for a mock)");
    }
}
