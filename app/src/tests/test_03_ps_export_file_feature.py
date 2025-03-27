import os
import subprocess
import hashlib
from google.cloud import storage
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
scenarios("../features/parallelstore_export_file.feature")

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

@given("a file is written to Parallelstore mount path")
def prepare_parallelstore_file(k8s_client):
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
    test_filename = f"test_data_transfer.txt"
    test_filepath = f"{mount_path}/{test_filename}"
    test_content = "Test data transfer between GCS and Parallelstore!"

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

@when("the file is exported from Parallelstore to the GCS bucket using gcloud")
def export_to_gcs():
    """Export data from Parallelstore to GCS using gcloud."""
    bucket_name = CONFIG["GCS"]["bucket_name"]
    mount_path = CONFIG["parallelstore"]["mount_path"]
    destination_path = f"gs://{bucket_name}/"
    instance_name = CONFIG["parallelstore"]["instance_name"]
    region = CONFIG["parallelstore"]["region"]

    command = [
        "gcloud", "beta", "parallelstore", "instances", "export-data",
        f"{instance_name}",
        f"--location={region}",
        f"--source-parallelstore-path=/",
        f"--destination-gcs-bucket-uri={destination_path}"
    ]

    logger.info("Starting export using gcloud...")
    logger.info(f"Running command: {' '.join(command)}")

    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        logger.error("Export failed!")
        logger.error(f"stdout:\n{result.stdout}")
        logger.error(f"stderr:\n{result.stderr}")
    else:
        logger.info("Export completed successfully.")
        logger.info(f"stdout:\n{result.stdout}")

    assert result.returncode == 0

@then("the files in Parallelstore should all be in GCS bucket")
def verify_file_in_gcs(k8s_client):
    """List files in the pod's Parallelstore mount path and verify they exist in the GCS bucket."""
    namespace = CONFIG["k8s"]["namespace"]
    mount_path = CONFIG["parallelstore"]["mount_path"]
    app_name = CONFIG["k8s"]["app_name"]
    bucket_name = CONFIG["GCS"]["bucket_name"]
    deployment_name = CONFIG["k8s"]["deployment_name"]
    core_api = k8s_client("CoreV1Api")
    
    # Log the beginning of the file listing process in the pod
    logger.info(f"Starting to list files inside pod at mount path '{mount_path}'...")

    core_api = k8s_client("CoreV1Api")
    pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=f"app={app_name}")
    assert pods.items, f"No pod found for deployment '{deployment_name}'."
    pod_name = pods.items[0].metadata.name

    logger.info(f"Checking if Parallelstore mount is accessible on pod '{pod_name}' at path '{mount_path}'...")

    exec_command = ["/bin/sh", "-c", f"find {mount_path} -type f | sed 's|^{mount_path}/||' | sed 's|^/||'"]

    try:
        output = stream(
            core_api.connect_get_namespaced_pod_exec,
            pod_name,
            namespace,
            command=exec_command,
            stderr=True, stdin=False,
            stdout=True, tty=False
        )
        files = output.strip().splitlines()
        logger.info(f"Files found in pod '{pod_name}': {files}")
    except Exception as e:
        logger.error(f"Error occurred while listing files in pod '{pod_name}': {str(e)}")
        raise

    # Now check that these files exist in the GCS bucket
    logger.info(f"Starting verification of files in the GCS bucket '{bucket_name}'...")

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)

    for filename in files:
        blob = bucket.blob(filename)  # No path needed, just the file name
        logger.info(f"Checking GCS blob: {filename}")
        
        try:
            if blob.exists():
                logger.info(f"File '{filename}' exists in GCS.")
            else:
                logger.warning(f"File '{filename}' not found in GCS!")
                raise FileNotFoundError(f"GCS blob '{filename}' not found.")
        except Exception as e:
            logger.error(f"Error occurred while checking '{filename}' in GCS: {str(e)}")
            raise

    logger.info("✅ All files in Parallelstore are found in GCS.")