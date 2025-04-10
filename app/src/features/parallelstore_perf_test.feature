Feature: Parallelstore Read Performance Testing

  Scenario: Successfully scale an exisitng deployment to 10,000 replicas and read to Parallelstore
    Given a GKE cluster is running
    And a deployment named "ps-perf" exists in the "ps" namespace
    And 100 files of 5MB each exist in the Parallelstore mount
    When the deployment has 5000 replicas up and running for 10 min
    Then the Parallelstore IOPS and throughput should be within the GCP official benchmarks after 10min test