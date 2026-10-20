package apiqa.framework.testng;

import java.util.LinkedHashMap;
import java.util.Map;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

import apiqa.framework.client.ApiResponse;
import apiqa.framework.context.Step;
import io.qameta.allure.Allure;

/** Every step's request and response attached to the Allure report as it happens; case id and priority as labels. */
final class AllureReporting {
    private static final ObjectMapper JSON = new ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT);

    private AllureReporting() {
    }

    static void attach(Step step) {
        ApiResponse response = step.response();
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("method", response.request().method());
        request.put("url", response.request().url());
        request.put("headers", response.request().headers());
        request.put("body", parsed(response.request().body()));
        Map<String, Object> answer = new LinkedHashMap<>();
        answer.put("status", response.statusCode());
        answer.put("elapsed_ms", response.elapsedMs());
        answer.put("body", parsed(response.body()));
        Map<String, Object> both = new LinkedHashMap<>();
        both.put("request", request);
        both.put("response", answer);
        String name = "step " + step.number() + ": " + response.request().method() + " " + response.request().url()
                + " -> " + response.statusCode();
        try {
            Allure.addAttachment(name, "application/json", JSON.writeValueAsString(both), ".json");
        } catch (JsonProcessingException error) {
            Allure.addAttachment(name, response.describe());
        }
    }

    static void label(String caseId, String priority) {
        if (caseId != null) {
            Allure.label("case_id", caseId);
            Allure.label("tag", "case " + caseId);
        }
        if (priority != null) {
            Allure.label("severity", TestLabels.SEVERITY_BY_PRIORITY.get(priority));
            Allure.label("tag", priority);
        }
    }

    private static Object parsed(String text) {
        if (text == null || text.isEmpty()) {
            return null;
        }
        try {
            return JSON.readTree(text);
        } catch (JsonProcessingException notJson) {
            return text;
        }
    }
}
