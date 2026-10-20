package apiqa.framework.expect;

/** An expectation that didn't hold. */
public class ExpectationFailed extends AssertionError {
    public ExpectationFailed(String message) {
        super(message);
    }
}
