"""Cases -> synthetic passenger records. Realistic, edge-heavy, privacy-safe
(obviously fake identities, @testdata.example emails). Tagged valid/edge/adversarial."""
import json
from .llm import get_client, extract_json

SYSTEM = (
    "You are a QA test-data engineer. Given a requirement and test cases, generate about "
    "{n} synthetic passenger booking records exercising those cases. "
    "Privacy-safe: OBVIOUSLY FAKE names and emails ending '@testdata.example'. "
    "Include valid, edge, adversarial records. Return ONLY a JSON array, no fences. "
    "Each: {{id, passenger_name, email, pnr, booking_time, cancel_time, payment_status, "
    "amount, category}}. category in: valid|edge|adversarial. pnr = 6 uppercase alphanumeric."
)


def generate_test_data(requirement, cases, n=10, client=None):
    client = client or get_client()
    user = f"Requirement:\n{requirement}\n\nTest cases:\n{json.dumps(cases, indent=2)}"
    return extract_json(client.complete(SYSTEM.format(n=n), user, max_tokens=4096))
