package apiqa.framework.context;

import apiqa.framework.client.ApiResponse;

/** One request and its response, numbered in the order the test made them. */
public record Step(int number, ApiResponse response) {
}
