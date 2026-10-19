"""Requirement -> structured test cases (positive/negative/edge/adversarial)."""
from .llm import get_client, extract_json

SYSTEM = (
    "You are a senior QA engineer. Given a requirement, produce test cases covering "
    "positive, negative, edge, and adversarial scenarios. Generate about {n} cases. "
    "Return ONLY a JSON array — no prose, no fences, no trailing commas. "
    "Each case: {{id, title, type, preconditions, steps (array, max 4), expected}}. "
    "type in: positive | negative | edge | adversarial. Keep fields concise."
)


def generate_test_cases(requirement, n=8, client=None):
    client = client or get_client()
    text = client.complete(SYSTEM.format(n=n), f"Requirement:\n{requirement}", max_tokens=4096)
    return extract_json(text)
