"""The API model: finding the operation a request calls, merging, saving."""

from qa_agent.api_model import ApiModel, Operation, load_api_model, save_api_model


def model() -> ApiModel:
    api = ApiModel()
    for operation in (Operation("GET", "/bookings/{pnr}", responses=[200, 404]),
                      Operation("GET", "/bookings/search", responses=[200]),
                      Operation("POST", "/bookings/{pnr}/cancel", responses=[200])):
        api.add("bookings", operation)
    return api


def test_a_path_with_a_captured_value_or_a_literal_value_finds_its_operation():
    api = model()
    assert api.find("bookings", "GET", "/bookings/{{pnr}}").path == "/bookings/{pnr}"
    assert api.find("bookings", "get", "/bookings/AB12CD").path == "/bookings/{pnr}"
    assert api.find("bookings", "POST", "/bookings/{{pnr}}/cancel").path == "/bookings/{pnr}/cancel"
    assert api.find("bookings", "GET", "/bookings/search?status=active").path == "/bookings/search"


def test_a_wrong_method_path_or_service_finds_nothing():
    api = model()
    assert api.find("bookings", "DELETE", "/bookings/{{pnr}}") is None
    assert api.find("bookings", "GET", "/bookings/{{pnr}}/refund") is None
    assert api.find("payments", "GET", "/bookings/{{pnr}}") is None


def test_the_same_operation_with_another_parameter_name_merges():
    api = model()
    assert api.add("bookings", Operation("POST", "/bookings/{id}/cancel", responses=[409])) is False
    assert api.find("bookings", "POST", "/bookings/X1/cancel").responses == [200, 409]
    assert api.count() == 3


def test_saved_and_loaded_the_model_is_the_same(tmp_path):
    api = model()
    save_api_model(api, tmp_path / "api.yaml")
    assert load_api_model(tmp_path / "api.yaml").to_dict() == api.to_dict()
