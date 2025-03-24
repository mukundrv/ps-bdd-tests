Scenario: Validate Parallelstore read performance metrics

    Given a GKE cluster is running
    And a deployment named "ps-test" exists in the "ps" namespace and it is running
    And a large test file is present on the mount path
    When the file is read for a period of time
    Then I can calculate and validate latency, IOPS, and throughput