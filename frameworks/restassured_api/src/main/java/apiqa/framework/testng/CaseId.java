package apiqa.framework.testng;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** The test case this test came from, e.g. {@code @CaseId("TC003")}: an Allure label and a TestNG attribute. */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface CaseId {
    String value();
}
