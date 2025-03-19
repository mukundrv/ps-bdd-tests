Feature: Parallelstore GKE Integration

  Scenario: Mounting Parallelstore on a GKE pod
    Given a GKE cluster is running
    And a deployment named "ps-test" exists in the "ps" namespace
    When the pod starts
    Then the Parallelstore mount should be accessible