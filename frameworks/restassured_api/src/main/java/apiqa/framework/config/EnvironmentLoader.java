package apiqa.framework.config;

import java.io.IOException;
import java.io.Reader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeSet;

import org.yaml.snakeyaml.Yaml;

/**
 * Reads environments.yaml, the same file the Python framework and env_check read.
 *
 * <pre>
 *   ./mvnw test -Denv=qa1                      the environment (or API_ENV=qa1); default: demo
 *   ./mvnw test -Dapi.config=path.yaml         the file (or API_CONFIG); default: config/environments.yaml
 * </pre>
 */
public final class EnvironmentLoader {
    public static final String DEFAULT_ENVIRONMENT = "demo";
    public static final String DEFAULT_CONFIG = "config/environments.yaml";
    private static final double DEFAULT_TIMEOUT_SECONDS = 10.0;

    private EnvironmentLoader() {
    }

    /** The environment chosen by -Denv / API_ENV, from the file chosen by -Dapi.config / API_CONFIG. */
    public static EnvironmentConfig fromSettings() {
        String name = setting("env", "API_ENV", DEFAULT_ENVIRONMENT);
        String path = setting("api.config", "API_CONFIG", DEFAULT_CONFIG);
        return load(Path.of(path), name);
    }

    @SuppressWarnings("unchecked")
    public static EnvironmentConfig load(Path path, String name) {
        if (!Files.isRegularFile(path)) {
            throw new ConfigException("environments file not found: " + path.toAbsolutePath());
        }
        Map<String, Object> data;
        try (Reader reader = Files.newBufferedReader(path)) {
            Object loaded = new Yaml().load(reader);
            data = loaded instanceof Map ? (Map<String, Object>) loaded : Map.of();
        } catch (IOException | RuntimeException error) {
            throw new ConfigException(path + ": not valid YAML (" + error.getMessage() + ")");
        }
        Map<String, Object> environments = asMap(data.get("environments"));
        if (!environments.containsKey(name)) {
            throw new ConfigException("unknown environment '" + name + "' in " + path + " (known: "
                    + String.join(", ", new TreeSet<>(environments.keySet())) + ")");
        }
        Map<String, Object> settings = asMap(environments.get(name));
        Map<String, String> services = new LinkedHashMap<>();
        asMap(settings.get("services")).forEach((service, url) -> services.put(service, String.valueOf(url)));
        if (services.isEmpty()) {
            throw new ConfigException("environment '" + name + "' lists no services");
        }
        String defaultService = String.valueOf(settings.getOrDefault("default_service", services.keySet().iterator().next()));
        if (!services.containsKey(defaultService)) {
            throw new ConfigException("environment '" + name + "': default_service '" + defaultService + "' is not one of its services");
        }
        double timeout = settings.containsKey("timeout_seconds")
                ? Double.parseDouble(String.valueOf(settings.get("timeout_seconds"))) : DEFAULT_TIMEOUT_SECONDS;
        boolean readOnly = Boolean.parseBoolean(String.valueOf(settings.getOrDefault("read_only", "false")));
        return new EnvironmentConfig(name, services, defaultService, asMap(settings.get("auth")), timeout, readOnly);
    }

    private static String setting(String property, String variable, String fallback) {
        String value = System.getProperty(property);
        if (value == null || value.isBlank()) {
            value = System.getenv(variable);
        }
        return value == null || value.isBlank() ? fallback : value;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        return value instanceof Map ? new LinkedHashMap<>((Map<String, Object>) value) : new LinkedHashMap<>();
    }
}
