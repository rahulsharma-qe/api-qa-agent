package apiqa.framework.testng;

import java.lang.reflect.Method;
import java.util.Arrays;

import org.testng.IHookCallBack;
import org.testng.IHookable;
import org.testng.ITestResult;
import org.testng.SkipException;
import org.testng.annotations.BeforeMethod;
import org.testng.annotations.Test;

import apiqa.framework.auth.TokenProvider;
import apiqa.framework.auth.TokenProviders;
import apiqa.framework.client.ApiClient;
import apiqa.framework.config.EnvironmentConfig;
import apiqa.framework.config.EnvironmentLoader;
import apiqa.framework.context.ScenarioContext;

/**
 * What every API test class extends. Gives {@code api()}, {@code apiFor("notifications")},
 * {@code context()} and {@code environment()}; skips a test in group {@code writes} on a read-only
 * environment, with the reason; labels the test with its {@code @CaseId} and {@code @Priority}.
 */
public abstract class BaseTest implements IHookable {
    public static final String WRITES_GROUP = "writes";
    private static final ThreadLocal<ScenarioContext> CONTEXT = new ThreadLocal<>();
    private static EnvironmentConfig environment;
    private static TokenProvider tokens;

    protected static synchronized EnvironmentConfig environment() {
        if (environment == null) {
            environment = EnvironmentLoader.fromSettings();
            tokens = TokenProviders.forEnvironment(environment);
        }
        return environment;
    }

    private static synchronized TokenProvider tokens() {
        environment();
        return tokens;
    }

    @BeforeMethod(alwaysRun = true)
    public void startScenario(ITestResult result) {
        environment();                         // a wrong environment or file stops here, with its message
        ScenarioContext context = new ScenarioContext(AllureReporting::attach);
        CONTEXT.set(context);
        result.setAttribute(ApiStepsListener.CONTEXT_ATTRIBUTE, context);
    }

    @Override
    public void run(IHookCallBack callBack, ITestResult result) {
        Method method = result.getMethod().getConstructorOrMethod().getMethod();
        String caseId = TestLabels.caseId(method);
        String priority = TestLabels.priority(method);
        if (caseId != null) {
            result.setAttribute("case_id", caseId);
        }
        if (priority != null) {
            result.setAttribute("priority", priority);
        }
        AllureReporting.label(caseId, priority);
        Test test = method.getAnnotation(Test.class);
        if (environment().readOnly() && test != null && Arrays.asList(test.groups()).contains(WRITES_GROUP)) {
            throw new SkipException("changes data; environment '" + environment().name() + "' is read-only");
        }
        callBack.runTestMethod(result);
    }

    /** A client for the environment's default service. */
    protected ApiClient api() {
        return new ApiClient(environment().baseUrl(), tokens(), context(), environment().timeoutSeconds());
    }

    /** A client for another service in the same environment. */
    protected ApiClient apiFor(String service) {
        return new ApiClient(environment().baseUrl(service), tokens(), context(), environment().timeoutSeconds());
    }

    /** Values carried between steps, and every step so far. Fresh for every test. */
    protected ScenarioContext context() {
        return CONTEXT.get();
    }
}
