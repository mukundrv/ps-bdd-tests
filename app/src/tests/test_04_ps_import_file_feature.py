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
scenarios("../features/parallelstore_import_file.feature")

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


@given("a file is written to GCS bucket")
def upload_file_to_gcs():
    """Upload a file to the GCS bucket."""
    bucket_name = CONFIG["GCS"]["bucket_name"]
    test_filename = "test_data_transfer.txt"
    test_content = "Test data transfer between GCS and Parallelstore!"
    
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(test_filename)

    logger.info(f"Uploading test file '{test_filename}' to GCS bucket '{bucket_name}'...")
    blob.upload_from_string(test_content)
    logger.info(f"File '{test_filename}' successfully uploaded to GCS.")


@when("the file is imported from GCS bucket to Parallelstore instance using gcloud")
def import_from_gcs():
    """Import data from GCS to Parallelstore using gcloud."""
    bucket_name = CONFIG["GCS"]["bucket_name"]
    instance_name = CONFIG["parallelstore"]["instance_name"]
    region = CONFIG["parallelstore"]["region"]
    source_path = f"gs://{bucket_name}/"
    mount_path = CONFIG["parallelstore"]["mount_path"]

    command = [
        "gcloud", "beta", "parallelstore", "instances", "import-data",
        f"{instance_name}",
        f"--location={region}",
        f"--source-gcs-bucket-uri={source_path}",
        f"--destination-parallelstore-path=/"
    ]

    logger.info("Starting import using gcloud...")
    logger.info(f"Running command: {' '.join(command)}")

    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        logger.error("Import failed!")
        logger.error(f"stdout:\n{result.stdout}")
        logger.error(f"stderr:\n{result.stderr}")
    else:
        logger.info("Import completed successfully.")
        logger.info(f"stdout:\n{result.stdout}")

    assert result.returncode == 0


@then("the files in GCS bucket should all be in Parallelstore")
def verify_files_in_parallelstore(k8s_client):
    """Verify that all files in the GCS bucket are also present in the Parallelstore mount path."""
    namespace = CONFIG["k8s"]["namespace"]
    mount_path = CONFIG["parallelstore"]["mount_path"]
    app_name = CONFIG["k8s"]["app_name"]
    bucket_name = CONFIG["GCS"]["bucket_name"]
    deployment_name = CONFIG["k8s"]["deployment_name"]
    core_api = k8s_client("CoreV1Api")

    # Log the beginning of the file listing process in the pod
    logger.info(f"Starting to list all files recursively inside pod at mount path '{mount_path}'...")

    # Get pod name
    pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=f"app={app_name}")
    assert pods.items, f"No pods found for app '{app_name}' in namespace '{namespace}'."
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
        parallelstore_files = output.strip().splitlines()
        logger.info(f"Files found in Parallelstore mount path '{mount_path}': {parallelstore_files}")
    except Exception as e:
        logger.error(f"Error occurred while listing files in Parallelstore mount path: {str(e)}")
        raise

    # Now check that these files exist in the GCS bucket
    logger.info(f"Starting verification of files in the GCS bucket '{bucket_name}'...")

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)

    # List files in the GCS bucket
    blobs = bucket.list_blobs()
    gcs_files = [blob.name for blob in blobs if not blob.name.endswith('/')]  # Filter out folder prefixes
    logger.info(f"Files found in GCS bucket '{bucket_name}': {gcs_files}")

    # Ensure every file in the GCS bucket is present in Parallelstore
    missing_files = [file for file in gcs_files if file not in parallelstore_files]

    if missing_files:
        logger.error(f"The following files are missing in Parallelstore: {missing_files}")
        raise FileNotFoundError(f"Files missing in Parallelstore: {missing_files}")
    else:
        logger.info("All files in the GCS bucket are present in Parallelstore.")