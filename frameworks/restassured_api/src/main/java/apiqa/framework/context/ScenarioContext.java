package apiqa.framework.context;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;
import java.util.function.Consumer;

import apiqa.framework.client.ApiResponse;

/**
 * Values carried from one step to the next, and every step so far (shown when a test fails).
 * <pre>
 *   String pnr = context().remember("pnr", created.text("pnr"));
 *   api().get("/bookings/" + context().get("pnr"));
 * </pre>
 */
public final class ScenarioContext {
    private final Map<String, Object> values = new LinkedHashMap<>();
    private final List<Step> steps = new ArrayList<>();
    private final Consumer<Step> onStep;

    public ScenarioContext() {
        this(step -> { });
    }

    /** onStep is told about each step as it happens, for example to attach it to a report. */
    public ScenarioContext(Consumer<Step> onStep) {
        this.onStep = onStep;
    }

    public <T> T remember(String name, T value) {
        values.put(name, value);
        return value;
    }

    public Object get(String name) {
        if (!values.containsKey(name)) {
            String known = values.isEmpty() ? "nothing yet" : String.join(", ", new TreeSet<>(values.keySet()));
            throw new IllegalStateException("'" + name + "' was never remembered (remembered: " + known + ")");
        }
        return values.get(name);
    }

    public List<Step> steps() {
        return Collections.unmodifiableList(steps);
    }

    public void record(ApiResponse response) {
        Step step = new Step(steps.size() + 1, response);
        steps.add(step);
        onStep.accept(step);
    }

    /** Every step's request and response, in order: the chain that led to a failure. */
    public String history() {
        if (steps.isEmpty()) {
            return "(no requests were made)";
        }
        StringBuilder text = new StringBuilder();
        for (Step step : steps) {
            text.append("step ").append(step.number()).append('\n').append(step.response().describe()).append('\n');
        }
        return text.toString().stripTrailing();
    }
}
