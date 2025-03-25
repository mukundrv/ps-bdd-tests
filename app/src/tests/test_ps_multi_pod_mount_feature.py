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

@when('I scale "ps-test" to 10 replicas')
def scale_deployment_to_1000(k8s_client):
    """Scale the deployment to 1000 replicas and monitor the progress."""
    namespace = CONFIG["k8s"]["namespace"]
    deployment_name = CONFIG["k8s"]["deployment_name"]
    replicas = 10
    timeout = CONFIG["scaling"]["timeout"]  # Timeout in seconds
    interval = 10  # Polling interval in seconds

    # Retrieve AppsV1Api client
    apps_api = k8s_client("AppsV1Api")
    logger.info(f"Scaling deployment '{deployment_name}' in namespace '{namespace}' to {replicas} replicas.")
    body = {"spec": {"replicas": replicas}}
    apps_api.patch_namespaced_deployment_scale(name=deployment_name, namespace=namespace, body=body)

    logger.info(f"Waiting for deployment '{deployment_name}' to reach {replicas} replicas...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        response = apps_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
        logger.debug(f"Current replicas: {response.status.replicas}, Available replicas: {response.status.available_replicas}")
        if (
            response.status.replicas == replicas
            and response.status.available_replicas == replicas
        ):
            logger.info(f"Deployment '{deployment_name}' successfully scaled to {replicas} replicas.")
            return
        time.sleep(interval)

    logger.error(f"Deployment '{deployment_name}' did not scale to {replicas} replicas within {timeout} seconds.")
    raise RuntimeError(f"Deployment '{deployment_name}' did not scale to {replicas} replicas within {timeout} seconds.")

@then("the Parallelstore mount should be accessible by all pods in the deployment")
def verify_parallelstore_mount(k8s_client):
    """Ensure the Parallelstore mount is accessible inside all pods of the deployment."""
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
        exec_command = ["/bin/sh", "-c", f"ls {mount_path} || echo 'ls failed'"]

        try:
            exec_response = stream(
                core_api.connect_get_namespaced_pod_exec,
                name=pod_name,
                namespace=namespace,
                command=exec_command,
                stderr=True, stdin=False, stdout=True, tty=False
            )

            if "ls failed" in exec_response:
                pytest.fail(f"Mount path '{mount_path}' is inaccessible in pod '{pod_name}'.")
            else:
                logger.info(f"Mount path '{mount_path}' is accessible in pod '{pod_name}'. Contents:\n{exec_response.strip() or '(empty)'}")

        except Exception as e:
            pytest.fail(f"Failed to access mount path in pod '{pod_name}': {str(e)}")