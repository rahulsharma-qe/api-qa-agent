package apiqa.framework.config;

import java.util.Collections;
import java.util.Map;
import java.util.TreeSet;

/** One environment from environments.yaml: where each service lives, how to authenticate, whether tests may change data. */
public final class EnvironmentConfig {
    private final String name;
    private final Map<String, String> services;
    private final String defaultService;
    private final Map<String, Object> auth;
    private final double timeoutSeconds;
    private final boolean readOnly;

    public EnvironmentConfig(String name, Map<String, String> services, String defaultService, Map<String, Object> auth,
                             double timeoutSeconds, boolean readOnly) {
        this.name = name;
        this.services = Collections.unmodifiableMap(services);
        this.defaultService = defaultService;
        this.auth = Collections.unmodifiableMap(auth);
        this.timeoutSeconds = timeoutSeconds;
        this.readOnly = readOnly;
    }

    public String name() { return name; }
    public Map<String, String> services() { return services; }
    public String defaultService() { return defaultService; }
    public Map<String, Object> auth() { return auth; }
    public double timeoutSeconds() { return timeoutSeconds; }
    public boolean readOnly() { return readOnly; }

    public String baseUrl() {
        return baseUrl(defaultService);
    }

    public String baseUrl(String service) {
        String url = services.get(service);
        if (url == null) {
            throw new ConfigException("environment '" + name + "' has no service '" + service + "' (it has: "
                    + String.join(", ", new TreeSet<>(services.keySet())) + ")");
        }
        return url.endsWith("/") ? url.substring(0, url.length() - 1) : url;
    }
}
