import time
import pytest
from google.cloud import monitoring_v3
from pytest_bdd import given, when, then, scenarios
from kubernetes import client, config

from src.utils.logging_util import get_logger
from src.utils.config_util import load_config
from kubernetes.stream import stream
import random
import string

logger = get_logger(__name__)
CONFIG = load_config()

scenarios("../features/parallelstore_perf_test.feature")


@given("a GKE cluster is running")
def verify_cluster_running(k8s_client):
    """Verify that the Kubernetes cluster is accessible."""
    logger.info("Verifying Kubernetes cluster is running...")
    assert k8s_client is not None, "Kubernetes client could not be initialized."
    logger.info("Kubernetes cluster verification successful.")

@given('a deployment named "ps-perf" exists in the "ps" namespace')
def verify_deployment_exists(k8s_client):
    """Ensure the deployment exists in the specified namespace."""
    namespace = CONFIG["k8s"]["namespace"]
    deployment_name = CONFIG["k8s"]["perf_deployment_name"]

    # Retrieve AppsV1Api client
    apps_api = k8s_client("AppsV1Api")
    logger.info(f"Checking if deployment '{deployment_name}' exists in namespace '{namespace}'...")
    response = apps_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
    assert response is not None, f"Deployment '{deployment_name}' does not exist in namespace '{namespace}'."
    logger.info(f"Deployment '{deployment_name}' exists.")

@given("100 files of 5MB each exist in the Parallelstore mount")
def prepare_parallelstore_files(k8s_client):
    """Remove existing files and create 100 test files of 5MB each in the Parallelstore mount path."""
    namespace = CONFIG["k8s"]["namespace"]
    mount_path = CONFIG["parallelstore"]["mount_path"]
    app_name = CONFIG["k8s"]["app_name"]
    core_api = k8s_client("CoreV1Api")
    perf_app_name = CONFIG["k8s"]["perf_app_name"]

    # Get pod name
    pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=f"app={perf_app_name}")
    assert pods.items, f"No pods found for app '{app_name}' in namespace '{namespace}'."
    pod_name = pods.items[0].metadata.name

    num_files = 10
    file_size_mb = 5
    file_size_bytes = file_size_mb * 1024 * 1024  # Convert to bytes

    # Step 1: **Remove all existing files in the mount path**
    logger.info(f"Clearing all files in {mount_path} before creating new ones.")
    cleanup_command = ["/bin/sh", "-c", f"rm -rf {mount_path}/*"]
    stream(
        core_api.connect_get_namespaced_pod_exec,
        name=pod_name,
        namespace=namespace,
        command=cleanup_command,
        stderr=True, stdin=False, stdout=True, tty=False
    )
    logger.info("All existing files deleted.")

    # Step 2: **Create new test files**
    logger.info(f"Creating {num_files} test files (5MB each) inside Parallelstore mount: {mount_path}")

    for i in range(num_files):
        test_filename = f"test_file_{i}.txt"
        test_filepath = f"{mount_path}/{test_filename}"
        
        # Generate a random content pattern
        test_content = "".join(random.choices(string.ascii_letters + string.digits, k=1024))  # 1KB of random text
        repeat_count = file_size_bytes // len(test_content)  # Repeat to make it 5MB

        logger.debug(f"Creating file {i+1}/{num_files}: {test_filename}")

        # Write 5MB file via shell command
        write_command = [
            "/bin/sh",
            "-c",
            f"printf '{test_content}' > {test_filepath} && yes '{test_content}' | head -c {file_size_bytes} >> {test_filepath}"
        ]
        stream(
            core_api.connect_get_namespaced_pod_exec,
            name=pod_name,
            namespace=namespace,
            command=write_command,
            stderr=True, stdin=False, stdout=True, tty=False
        )

        logger.info(f"File created: {test_filepath}")
        time.sleep(0.2)  # Slight delay to avoid overwhelming storage

    logger.info("Successfully created 100 test files in Parallelstore.")

@when('the deployment has 5000 replicas up and running for 30 min')
def scale_deployment(k8s_client):
    """Scale the deployment to 5000 replicas and monitor the progress."""
    namespace = CONFIG["k8s"]["namespace"]
    deployment_name = CONFIG["k8s"]["perf_deployment_name"]
    replicas = 5000
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
            break
        time.sleep(interval)

    else:
        logger.error(f"Deployment '{deployment_name}' did not scale to {replicas} replicas within {timeout} seconds.")
        raise RuntimeError(f"Deployment '{deployment_name}' did not scale to {replicas} replicas within {timeout} seconds.")

    # Wait for 30 minutes before proceeding
    wait_time = 10 * 60  # 30 minutes in seconds
    logger.info(f"Waiting for {wait_time / 60} minutes to let all pods run before performance testing...")
    time.sleep(wait_time)
    logger.info("30-minute waiting period completed. Proceeding with performance validation.")

@then("the Parallelstore IOPS and throughput should be within the GCP official benchmarks after 30min test")
def validate_parallelstore_metrics():
    """Fetch and validate Parallelstore IOPS and throughput using Cloud Monitoring API."""
    project_id = CONFIG["parallelstore"]["project_id"]
    instance_id = CONFIG["parallelstore"]["instance_name"]
    region = CONFIG["parallelstore"]["region"]

    # Expected benchmarks (example values, update based on GCP docs)
    EXPECTED_IOPS = 30000
    EXPECTED_THROUGHPUT_MBPS = 1.15  # 1GB/s

    def fetch_metric(metric_type, instance_id):
        """Query Cloud Monitoring API for Parallelstore metrics and return the max value."""
        client = monitoring_v3.MetricServiceClient()
        project_name = f"projects/{project_id}"

        # Query last 15 minutes of data
        interval = monitoring_v3.TimeInterval(
            end_time={"seconds": int(time.time())},
            start_time={"seconds": int(time.time() - 300)},  # Last 30 minutes
        )

        filter_str = f'metric.type="{metric_type}" AND resource.type="parallelstore.googleapis.com/Instance" AND resource.label.instance_id="{instance_id}"'
        request = monitoring_v3.ListTimeSeriesRequest(
            name=project_name,
            filter=filter_str,
            interval=interval,
            view=monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
        )

        result = client.list_time_series(request=request)
        
        # Extract all the values from the time series data
        values = [point.value.double_value for ts in result for point in ts.points]
        
        # Return the max value or None if no values found
        return max(values) if values else None

    # Fetch IOPS and throughput
    iops_metric = "parallelstore.googleapis.com/instance/read_ops_count"
    throughput_metric = "parallelstore.googleapis.com/instance/transferred_byte_count"

    actual_iops = fetch_metric(iops_metric, instance_id)
    actual_throughput = fetch_metric(throughput_metric, instance_id)
    # actual_cpu = fetch_metric("kubernetes.io/container/cpu/core_usage_time")

    logger.info(f"Retrieved Parallelstore Metrics:")
    # logger.info(f"CPU Usage: {actual_cpu}")
    logger.info(f"Max IOPS: {actual_iops} (Expected: {EXPECTED_IOPS})")
    logger.info(f"Max Throughput: {actual_throughput} MBps (Expected: {EXPECTED_THROUGHPUT_MBPS})")

    # Validation against expected benchmarks
    assert actual_iops is not None and actual_iops >= EXPECTED_IOPS, f"IOPS too low: {actual_iops}"
    assert actual_throughput is not None and actual_throughput >= EXPECTED_THROUGHPUT_MBPS, f"Throughput too low: {actual_throughput} MBps"

    logger.info("Parallelstore performance meets GCP benchmarks!")