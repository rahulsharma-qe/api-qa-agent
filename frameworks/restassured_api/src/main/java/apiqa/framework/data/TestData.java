package apiqa.framework.data;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.ss.usermodel.WorkbookFactory;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Test data from files, one row per map. CSV and Excel cells become numbers, true/false and null
 * (empty) where they look like them; JSON is read as written (a list of objects, or {"rows": [...]}).
 * <pre>
 *   &#64;DataProvider public Object[][] boundaries() { return TestData.asDataProvider(TestData.rows("data/x.xlsx")); }
 * </pre>
 */
public final class TestData {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final SecureRandom RANDOM = new SecureRandom();

    private TestData() {
    }

    /**
     * Six characters, new on every call (7f3a9c): for names and emails no other test is using, so tests
     * don't collide on an environment other teams share.
     */
    public static String uniqueId() {
        byte[] bytes = new byte[3];
        RANDOM.nextBytes(bytes);
        return HexFormat.of().formatHex(bytes);
    }

    public static List<Map<String, Object>> rows(String path) {
        Path file = Path.of(path);
        if (!Files.isRegularFile(file)) {
            throw new IllegalArgumentException("test data file not found: " + file.toAbsolutePath());
        }
        String name = file.getFileName().toString().toLowerCase();
        try {
            if (name.endsWith(".csv")) {
                return csvRows(Files.readAllLines(file, StandardCharsets.UTF_8));
            }
            if (name.endsWith(".xlsx") || name.endsWith(".xls")) {
                return excelRows(file);
            }
            if (name.endsWith(".json")) {
                return jsonRows(file);
            }
        } catch (IOException error) {
            throw new IllegalArgumentException("cannot read " + file + ": " + error.getMessage(), error);
        }
        throw new IllegalArgumentException(file + ": use .csv, .xlsx or .json");
    }

    /** One TestNG data-provider row per data row, each holding the row's map. */
    public static Object[][] asDataProvider(List<Map<String, Object>> rows) {
        Object[][] provided = new Object[rows.size()][];
        for (int i = 0; i < rows.size(); i++) {
            provided[i] = new Object[] {rows.get(i)};
        }
        return provided;
    }

    static Object typed(String text) {
        if (text == null) {
            return null;
        }
        String value = text.trim();
        if (value.isEmpty()) {
            return null;
        }
        if (value.equalsIgnoreCase("true") || value.equalsIgnoreCase("false")) {
            return Boolean.parseBoolean(value);
        }
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException notInteger) {
            // try a decimal next
        }
        try {
            return Double.parseDouble(value);
        } catch (NumberFormatException notNumber) {
            return value;
        }
    }

    private static List<Map<String, Object>> csvRows(List<String> lines) {
        List<Map<String, Object>> rows = new ArrayList<>();
        if (lines.isEmpty()) {
            return rows;
        }
        List<String> header = splitCsvLine(lines.get(0));
        for (String line : lines.subList(1, lines.size())) {
            if (line.isBlank()) {
                continue;
            }
            List<String> cells = splitCsvLine(line);
            Map<String, Object> row = new LinkedHashMap<>();
            for (int i = 0; i < header.size(); i++) {
                row.put(header.get(i).trim(), typed(i < cells.size() ? cells.get(i) : ""));
            }
            rows.add(row);
        }
        return rows;
    }

    /** Commas separate cells; a cell in double quotes may contain commas, and "" is a quote. */
    private static List<String> splitCsvLine(String line) {
        List<String> cells = new ArrayList<>();
        StringBuilder cell = new StringBuilder();
        boolean quoted = false;
        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);
            if (quoted && c == '"' && i + 1 < line.length() && line.charAt(i + 1) == '"') {
                cell.append('"');
                i++;
            } else if (c == '"') {
                quoted = !quoted;
            } else if (c == ',' && !quoted) {
                cells.add(cell.toString());
                cell.setLength(0);
            } else {
                cell.append(c);
            }
        }
        cells.add(cell.toString());
        return cells;
    }

    private static List<Map<String, Object>> excelRows(Path file) throws IOException {
        List<Map<String, Object>> rows = new ArrayList<>();
        DataFormatter formatter = new DataFormatter();
        try (InputStream input = Files.newInputStream(file); Workbook book = WorkbookFactory.create(input)) {
            Sheet sheet = book.getSheetAt(0);
            Row headerRow = sheet.getRow(sheet.getFirstRowNum());
            if (headerRow == null) {
                return rows;
            }
            List<String> header = new ArrayList<>();
            for (Cell cell : headerRow) {
                header.add(formatter.formatCellValue(cell).trim());
            }
            for (int r = sheet.getFirstRowNum() + 1; r <= sheet.getLastRowNum(); r++) {
                Row row = sheet.getRow(r);
                if (row == null) {
                    continue;
                }
                Map<String, Object> values = new LinkedHashMap<>();
                boolean anyValue = false;
                for (int c = 0; c < header.size(); c++) {
                    Object value = typed(formatter.formatCellValue(row.getCell(c)));
                    anyValue |= value != null;
                    values.put(header.get(c), value);
                }
                if (anyValue) {
                    rows.add(values);
                }
            }
        }
        return rows;
    }

    private static List<Map<String, Object>> jsonRows(Path file) throws IOException {
        JsonNode root = JSON.readTree(file.toFile());
        JsonNode list = root.isObject() && root.has("rows") ? root.get("rows") : root;
        if (!list.isArray()) {
            throw new IllegalArgumentException(file + ": expected a list of objects, or {\"rows\": [...]}");
        }
        return JSON.convertValue(list, new TypeReference<List<Map<String, Object>>>() { });
    }
}
