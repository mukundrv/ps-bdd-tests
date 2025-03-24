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
scenarios("../features/parallelstore_multi_pod_mount.feature")


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

@then("the Parallelstore mount should be accessible by all pods in the deployment")
def verify_parallelstore_mount(k8s_client):
    """Ensure the Parallelstore mount is accessible inside the pod."""
    namespace = CONFIG["k8s"]["namespace"]
    deployment_name = CONFIG["k8s"]["deployment_name"]
    mount_path = CONFIG["parallelstore"]["mount_path"]
    app_name = CONFIG["k8s"]["app_name"]

    core_api = k8s_client("CoreV1Api")
    pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=f"app={app_name}")

    assert pods.items, "No pods found for the deployment."

    for pod in pods.items:
        pod_name = pod.metadata.name
        logger.info(f"Checking mount access in pod '{pod_name}' at path '{mount_path}'...")
        exec_command = ["/bin/sh", "-c", f"ls {mount_path}"]

        try:
            exec_response = stream(
                core_api.connect_get_namespaced_pod_exec,
                name=pod_name,
                namespace=namespace,
                command=exec_command,
                stderr=True, stdin=False, stdout=True, tty=False
            )
            assert exec_response.strip(), f"Mount path '{mount_path}' is empty or inaccessible in pod '{pod_name}'."
            logger.info(f"Mount path accessible in pod '{pod_name}'.")
        except Exception as e:
            pytest.fail(f"Failed to access mount path in pod '{pod_name}': {str(e)}")