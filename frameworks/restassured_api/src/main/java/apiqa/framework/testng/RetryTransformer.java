package apiqa.framework.testng;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Locale;

import org.testng.IAnnotationTransformer;
import org.testng.annotations.ITestAnnotation;

/**
 * Registered in the pom, so no test has to ask for these:
 * every test gets the RetryOnce analyzer, and a test with {@code @Priority("P0")} joins the group
 * {@code p0}, so {@code -Dgroups=p0} runs the P0 tests (generated or written by hand).
 * The class keeps its name: the teams' poms register it by it.
 */
public class RetryTransformer implements IAnnotationTransformer {
    @Override
    @SuppressWarnings("rawtypes")
    public void transform(ITestAnnotation annotation, Class testClass, Constructor testConstructor, Method testMethod) {
        annotation.setRetryAnalyzer(RetryOnce.class);
        Priority priority = testMethod == null ? null : testMethod.getAnnotation(Priority.class);
        if (priority != null) {
            annotation.setGroups(withGroup(annotation.getGroups(), priority.value().toLowerCase(Locale.ROOT)));
        }
    }

    public static String[] withGroup(String[] groups, String group) {
        if (Arrays.asList(groups).contains(group)) {
            return groups;
        }
        String[] all = Arrays.copyOf(groups, groups.length + 1);
        all[groups.length] = group;
        return all;
    }
}
