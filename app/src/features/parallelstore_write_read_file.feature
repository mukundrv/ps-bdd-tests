Feature: Parallelstore Write and Read File

Scenario: Verify Parallelstore mount supports read and write operations
    Given a GKE cluster is running
    And a deployment named "ps-test" exists in the "ps" namespace
    When the deployment starts
    Then a file can be written to and read from the Parallelstore mount