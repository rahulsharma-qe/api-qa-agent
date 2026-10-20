@cancellation
Feature: Cancellation scenarios

  @TC040 @AC-2 @AC-3 @P0
  Scenario Outline: The refund depends on when the booking is cancelled
    When I POST "/bookings" with
      """
      {"passenger_name": "Asha Rao {{unique}}", "email": "asha.{{unique}}@testdata.example", "amount": 250, "booked_at": "<booked_at>"}
      """
    Then the status is 201
    And I remember "pnr" as "pnr"
    When I POST "/bookings/{{pnr}}/cancel" with
      """
      {"cancelled_at": "<cancelled_at>"}
      """
    Then the status is 200
    And "refund_allowed" is <refund_allowed>
    And "refund_amount" is <refund_amount>

    Examples:
      | booked_at            | cancelled_at         | refund_allowed | refund_amount |
      | 2026-01-15T10:00:00Z | 2026-01-15T22:00:00Z | true           | 250           |
      | 2026-01-15T10:00:00Z | 2026-01-17T10:00:00Z | false          | 0             |

  @TC041 @AC-4 @P2
  Scenario: Cancelling twice tells the passenger it is already cancelled
    Given a booking that has been cancelled
    When the passenger cancels it again
    Then they are told it is already cancelled, and nothing changes
