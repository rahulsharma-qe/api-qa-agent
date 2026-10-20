"""Gherkin: scenarios in the fixed phrasing become steps; any other scenario stays in words."""

from qa_agent.importers.gherkin import read_feature_file

FEATURE = '''@cancellation
Feature: Cancellation scenarios

  Background:
    When I POST "/bookings" with
      """
      {"amount": 250, "booked_at": "<booked_at>"}
      """
    Then the status is 201
    And I remember "pnr" as "pnr"

  @TC040 @AC-2 @P0
  Scenario Outline: Refund by time
    When I POST "/bookings/{{pnr}}/cancel" with
      """
      {"cancelled_at": "<cancelled_at>"}
      """
    Then the status is <status>
    And "refund_allowed" is <allowed>
    And "reason" is "on time"

    Examples:
      | booked_at | cancelled_at | status | allowed |
      | t1        | t2           | 200    | true    |

  @AC-4
  Scenario: Cancel twice
    Given a cancelled booking
    When it is cancelled again
    Then it is refused
'''


def test_a_scenario_in_the_fixed_phrasing_becomes_steps_with_its_data(tmp_path):
    path = tmp_path / "cancel.feature"
    path.write_text(FEATURE)
    feature = read_feature_file(path, "existing/cancel.feature").features[0]
    outline = feature.cases[0]
    assert (outline["id"], outline["criteria"], outline["priority"], outline["tags"]) == \
        ("TC040", ["AC-2"], "P0", ["cancellation"])
    create, cancel = outline["steps"]
    assert create == {"request": {"method": "POST", "path": "/bookings",
                                  "body": {"amount": 250, "booked_at": "{{row.booked_at}}"}},
                      "expect": {"status": 201}, "capture": {"pnr": "pnr"}}
    assert cancel["expect"] == {"status": "{{row.status}}",
                                "fields": {"refund_allowed": "{{row.allowed}}", "reason": "on time"}}
    assert outline["data"] == "data/cancellation-scenarios-tc040.csv"
    assert feature.data_files[outline["data"]] == [{"booked_at": "t1", "cancelled_at": "t2", "status": "200",
                                                    "allowed": "true"}]


def test_any_other_scenario_is_kept_in_words(tmp_path):
    path = tmp_path / "cancel.feature"
    path.write_text(FEATURE)
    result = read_feature_file(path, "existing/cancel.feature")
    words = result.features[0].cases[1]
    assert words["id"] == "CANCELLATION-SCENARIOS-02"
    assert words["steps_text"][-3:] == ["Given a cancelled booking", "When it is cancelled again", "Then it is refused"]
    assert "steps" not in words and "kept in words" in result.notes[0]
