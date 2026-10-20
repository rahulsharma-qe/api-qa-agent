package apiqa.framework.testng;

import java.lang.reflect.Method;
import java.util.Map;

/** Reads @CaseId and @Priority from a test method. */
final class TestLabels {
    static final Map<String, String> SEVERITY_BY_PRIORITY = Map.of("P0", "blocker", "P1", "critical", "P2", "normal", "P3", "minor");

    private TestLabels() {
    }

    static String caseId(Method method) {
        CaseId caseId = method.getAnnotation(CaseId.class);
        return caseId == null ? null : caseId.value();
    }

    static String priority(Method method) {
        Priority priority = method.getAnnotation(Priority.class);
        if (priority == null) {
            return null;
        }
        String level = priority.value().toUpperCase();
        if (!SEVERITY_BY_PRIORITY.containsKey(level)) {
            throw new IllegalArgumentException(method.getDeclaringClass().getSimpleName() + "." + method.getName()
                    + ": priority must be one of P0, P1, P2, P3, not '" + priority.value() + "'");
        }
        return level;
    }
}
