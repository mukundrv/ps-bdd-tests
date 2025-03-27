Feature: Parallelstore GCS Data Transfer Export

  Scenario: Export file from Parallelstore to GCS
    Given a GKE cluster is running
    And a deployment named "ps-test" exists in the "ps" namespace
    And a file is written to Parallelstore mount path
    When the file is exported from Parallelstore to the GCS bucket using gcloud
    Then the files in Parallelstore should all be in GCS bucket