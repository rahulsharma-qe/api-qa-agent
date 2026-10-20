package apiqa.framework.client;

/** A path that isn't in the response. Fails the test with the path, the request and the response. */
public class FieldNotFound extends AssertionError {
    public FieldNotFound(String message) {
        super(message);
    }
}
