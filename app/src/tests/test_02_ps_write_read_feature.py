import pytest
from pytest_bdd import given, when, then, scenarios
from src.utils.logging_util import get_logger
import time
from src.utils.config_util import load_config
from kubernetes.stream import stream

logger = get_logger(__name__)
# Load configuration once at module level
CONFIG = load_config()
# Link the Gherkin feature file
scenarios("../features/parallelstore_write_read_file.feature")


@given("a GKE cluster is running")
def verify_cluster_running(k8s_client):
    """Verify that the Kubernetes cluster is accessible."""
    logger.info("Verifying Kubernetes cluster is running...")
    assert k8s_client is not None, "Kubernetes client could not be initialized."
    logger.info("Kubernetes cluster verification successful.")


@given('a deployment named "ps-test" exists in the "ps" namespace')
def verify_deployment_exists(k8s_client):
    """Ensure the deployment exists in the specified namespace."""
    namespace = CONFIG["k8s"]["namespace"]
    deployment_name = CONFIG["k8s"]["deployment_name"]

    # Retrieve AppsV1Api client
    apps_api = k8s_client("AppsV1Api")
    logger.info(f"Checking if deployment '{deployment_name}' exists in namespace '{namespace}'...")
    response = apps_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
    assert response is not None, f"Deployment '{deployment_name}' does not exist in namespace '{namespace}'."
    logger.info(f"Deployment '{deployment_name}' exists.")

@when('the deployment starts')
def verify_pod_running(k8s_client):
    """Ensure the pod for the deployment is running."""
    namespace = CONFIG["k8s"]["namespace"]
    deployment_name = CONFIG["k8s"]["deployment_name"]
    app_name = CONFIG["k8s"]["app_name"]

    # Retrieve CoreV1Api client for Pod checks
    core_api = k8s_client("CoreV1Api")

    retries = 5  # Retry up to 10 times (adjust as needed)
    for _ in range(retries):
        logger.info(f"Checking if pod for deployment '{deployment_name}' is running...")
        pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=f"app={app_name}")
        for pod in pods.items:
            if pod.status.phase == "Running":
                logger.info(f"Pod '{pod.metadata.name}' is running.")
                return pod.metadata.name
        time.sleep(5)  # Wait before retrying
    
    pytest.fail(f"Pod for deployment '{deployment_name}' did not start running.")

@then("a file can be written to and read from the Parallelstore mount")
def test_parallelstore_read_write(k8s_client):
    """Test read and write operations on the Parallelstore mount."""
    namespace = CONFIG["k8s"]["namespace"]
    mount_path = CONFIG["parallelstore"]["mount_path"]
    app_name = CONFIG["k8s"]["app_name"]
    core_api = k8s_client("CoreV1Api")

    # Get pod name
    pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=f"app={app_name}")
    assert pods.items, f"No pods found for app '{app_name}' in namespace '{namespace}'."
    pod_name = pods.items[0].metadata.name

    # Generate a unique test file name
    test_filename = f"test_file.txt"
    test_filepath = f"{mount_path}/{test_filename}"
    test_content = "Hello Parallelstore!"

    # Step 1: Write a file to the mount path
    logger.info(f"Writing test file '{test_filename}' to Parallelstore...")
    write_command = ["/bin/sh", "-c", f"echo '{test_content}' > {test_filepath}"]
    stream(
        core_api.connect_get_namespaced_pod_exec,
        name=pod_name,
        namespace=namespace,
        command=write_command,
        stderr=True, stdin=False, stdout=True, tty=False
    )

    # Step 2: Read the file back
    logger.info(f"Reading test file '{test_filename}' from Parallelstore...")
    read_command = ["/bin/sh", "-c", f"cat {test_filepath}"]
    read_response = stream(
        core_api.connect_get_namespaced_pod_exec,
        name=pod_name,
        namespace=namespace,
        command=read_command,
        stderr=True, stdin=False, stdout=True, tty=False
    )

    assert read_response.strip() == test_content, \
        f"Content mismatch. Expected: '{test_content}', Got: '{read_response.strip()}'"
    logger.info("Read/write test passed.")