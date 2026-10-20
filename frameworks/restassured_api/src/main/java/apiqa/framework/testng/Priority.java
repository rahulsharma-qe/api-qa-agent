package apiqa.framework.testng;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** P0 (highest) to P3: the severity in Allure (P0 blocker, P1 critical, P2 normal, P3 minor) and a TestNG attribute. */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Priority {
    String value();
}
