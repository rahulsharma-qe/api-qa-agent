"""The framework never imports the service it tests: expected values come from the test or its
data, so a mistake in the service is caught instead of copied."""

from pathlib import Path

FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]


def test_nothing_in_the_framework_imports_the_mock_service():
    offenders = [str(path.relative_to(FRAMEWORK_ROOT)) for path in FRAMEWORK_ROOT.rglob("*.py")
                 if "mock_service" in path.read_text(encoding="utf-8") and path.name != Path(__file__).name]
    assert offenders == [], f"these files mention mock_service: {offenders}"
