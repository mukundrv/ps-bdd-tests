Feature: Parallelstore Multi Pod Mount GKE

  Scenario: Mounting Parallelstore on multiple GKE pods and they all can access to the mount point
    Given a GKE cluster is running
    And a deployment named "ps-test" exists in the "ps" namespace
    When I scale "ps-test" to 10 replicas
    Then the Parallelstore mount should be accessible by all pods in the deployment