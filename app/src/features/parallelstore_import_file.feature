Feature: Parallelstore GCS Data Transfer Import

  Scenario: Import file from Parallelstore to GCS
    Given a GKE cluster is running
    And a deployment named "ps-test" exists in the "ps" namespace
    And a file is written to GCS bucket
    When the file is imported from GCS bucket to Parallelstore instance using gcloud
    Then the files in GCS bucket should all be in Parallelstore