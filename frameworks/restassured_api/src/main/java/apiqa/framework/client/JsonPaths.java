package apiqa.framework.client;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import com.fasterxml.jackson.databind.JsonNode;

/** Follows "a.b[0].c" through a JSON document, the same way the Python framework does. */
public final class JsonPaths {
    private static final Pattern PART = Pattern.compile("^([^\\[\\]]*)((?:\\[\\d+])*)$");
    private static final Pattern INDEX = Pattern.compile("\\[(\\d+)]");

    private JsonPaths() {
    }

    /** The node at the path, or empty when any step isn't there. */
    public static Optional<JsonNode> find(JsonNode root, String path) {
        JsonNode current = root;
        for (String part : path.split("\\.")) {
            Matcher match = PART.matcher(part);
            if (current == null || !match.matches()) {
                return Optional.empty();
            }
            String key = match.group(1);
            if (!key.isEmpty()) {
                if (!current.isObject() || !current.has(key)) {
                    return Optional.empty();
                }
                current = current.get(key);
            }
            for (int index : indexes(match.group(2))) {
                if (!current.isArray() || index >= current.size()) {
                    return Optional.empty();
                }
                current = current.get(index);
            }
        }
        return Optional.ofNullable(current);
    }

    private static List<Integer> indexes(String text) {
        List<Integer> found = new ArrayList<>();
        Matcher match = INDEX.matcher(text);
        while (match.find()) {
            found.add(Integer.parseInt(match.group(1)));
        }
        return found;
    }
}
