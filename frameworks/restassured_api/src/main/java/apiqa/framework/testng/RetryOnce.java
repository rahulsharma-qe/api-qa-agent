package apiqa.framework.testng;

import org.testng.IRetryAnalyzer;
import org.testng.ITestResult;

/** With -Dretry=1, a failed test runs once more. A pass on retry is reported separately, never as a plain pass. */
public class RetryOnce implements IRetryAnalyzer {
    private int attempts;

    @Override
    public boolean retry(ITestResult result) {
        int allowed = Integer.getInteger("retry", 0);
        if (attempts < allowed) {
            attempts++;
            return true;
        }
        return false;
    }
}
