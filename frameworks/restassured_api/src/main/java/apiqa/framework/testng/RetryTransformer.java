package apiqa.framework.testng;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;

import org.testng.IAnnotationTransformer;
import org.testng.annotations.ITestAnnotation;

/** Gives every test the RetryOnce analyzer, so no test has to ask for it. Registered in the pom. */
public class RetryTransformer implements IAnnotationTransformer {
    @Override
    @SuppressWarnings("rawtypes")
    public void transform(ITestAnnotation annotation, Class testClass, Constructor testConstructor, Method testMethod) {
        annotation.setRetryAnalyzer(RetryOnce.class);
    }
}
