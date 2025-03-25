Scenario: Perform 30-minute read-only test from 5000 pods on prewritten files
    Given a GKE cluster is running
    And a deployment named "ps-test" exists in the "ps" namespace
    And 10 files of 5MB each are pre-written to the Parallelstore mount
    When I scale "ps-test" to 5000 replicas
    And every pod randomly reads files randomly for 30 minutes at the same time
    Then I collect and report the average IOPS and throughput for all pods