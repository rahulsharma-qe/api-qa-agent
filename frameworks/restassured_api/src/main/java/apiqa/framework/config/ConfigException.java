package apiqa.framework.config;

/** environments.yaml is missing, malformed, or doesn't have what a test asked for. Stops the run with a clear message. */
public class ConfigException extends RuntimeException {
    public ConfigException(String message) {
        super(message);
    }
}
