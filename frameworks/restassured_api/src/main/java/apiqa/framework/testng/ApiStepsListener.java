package apiqa.framework.testng;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Set;

import org.testng.ITestContext;
import org.testng.ITestListener;
import org.testng.ITestResult;
import org.testng.Reporter;

import apiqa.framework.context.ScenarioContext;

/**
 * After each test: on a failure, every request and response in order; with {@code -Devidence=folder},
 * one evidence file per test, pass, fail or skipped; a pass after a retry listed separately.
 */
public class ApiStepsListener implements ITestListener {
    static final String CONTEXT_ATTRIBUTE = "scenario_context";
    private static final Set<String> RETRIED = new LinkedHashSet<>();
    private static final Set<String> PASSED_ON_RETRY = new LinkedHashSet<>();

    @Override
    public void onTestSuccess(ITestResult result) {
        String outcome = "passed";
        if (RETRIED.contains(key(result))) {
            outcome = "passed on retry";
            PASSED_ON_RETRY.add(key(result));
            result.setAttribute("passed_on_retry", "true");
        }
        writeEvidence(result, outcome);
    }

    @Override
    public void onTestFailure(ITestResult result) {
        ScenarioContext context = context(result);
        if (context != null && !context.steps().isEmpty()) {
            String chain = "---- API steps, in order: " + name(result) + " ----\n" + context.history();
            System.out.println(chain);
            Reporter.log(chain.replace("\n", "<br>"), false);
        }
        writeEvidence(result, "failed");
    }

    @Override
    public void onTestSkipped(ITestResult result) {
        if (result.wasRetried()) {
            RETRIED.add(key(result));
            return;                                   // the retry decides the result
        }
        writeEvidence(result, "skipped");
    }

    @Override
    public void onFinish(ITestContext testContext) {
        if (!PASSED_ON_RETRY.isEmpty()) {
            System.out.println("==== Passed on retry: look at these, they may be flaky ====");
            PASSED_ON_RETRY.forEach(test -> System.out.println("  " + test));
        }
    }

    private static void writeEvidence(ITestResult result, String outcome) {
        String folder = System.getProperty("evidence");
        if (folder == null || folder.isBlank()) {
            return;
        }
        ScenarioContext context = context(result);
        StringBuilder text = new StringBuilder()
                .append("test:    ").append(name(result)).append('\n')
                .append("case:    ").append(result.getAttribute("case_id") == null ? "-" : result.getAttribute("case_id")).append('\n')
                .append("result:  ").append(outcome).append("\n\n")
                .append(context == null ? "(this test made no API calls)" : context.history()).append('\n');
        if (result.getThrowable() != null && !outcome.startsWith("passed")) {
            text.append("\nfailure:\n").append(result.getThrowable().getMessage()).append('\n');
        }
        try {
            Path directory = Path.of(folder);
            Files.createDirectories(directory);
            Files.writeString(directory.resolve(name(result).replaceAll("[^A-Za-z0-9_.-]+", "_") + ".txt"),
                    text.toString(), StandardCharsets.UTF_8);
        } catch (IOException error) {
            System.err.println("could not write evidence for " + name(result) + ": " + error.getMessage());
        }
    }

    private static ScenarioContext context(ITestResult result) {
        Object context = result.getAttribute(CONTEXT_ATTRIBUTE);
        return context instanceof ScenarioContext ? (ScenarioContext) context : null;
    }

    private static String name(ITestResult result) {
        String parameters = result.getParameters().length == 0 ? "" : Arrays.deepToString(result.getParameters());
        return result.getTestClass().getRealClass().getSimpleName() + "." + result.getMethod().getMethodName() + parameters;
    }

    private static String key(ITestResult result) {
        return name(result);
    }
}
