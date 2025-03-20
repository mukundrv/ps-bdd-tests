import tomli
from kubernetes import client, config
from kubernetes.client.configuration import Configuration
from kubernetes.client.api_client import ApiClient
from src.utils.logging_util import get_logger
import urllib3
import base64

logger = get_logger(__name__)

class KubernetesClient:
    """
    Utility class to set up and provide Kubernetes API clients.
    """

    def __init__(self, config_file="config/settings.toml"):
        """
        Initializes the Kubernetes client based on configuration.

        Args:
            config_file (str): Path to the configuration file.
        """
        self.config = self._load_config(config_file)
        self.k8s_config = {}
        self.api_clients = {}  # Cache for API clients
        self._initialize_client()
        self.api_clients = {}

    def _load_config(self, config_file):
        """
        Load the configuration from the given TOML file.

        Args:
            config_file (str): Path to the configuration file.

        Returns:
            dict: Parsed configuration data.
        """
        logger.info(f"Loading configuration from {config_file}...")
        try:
            with open(config_file, "rb") as file:
                config_data = tomli.load(file)
                logger.info("Configuration loaded successfully.")
                return config_data
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {config_file}.")
            raise
        except Exception as e:
            logger.exception(f"Failed to load configuration: {e}")
            raise

    def _initialize_client(self):
        """
        Initializes the Kubernetes client based on the configuration.
        """
        try:
            logger.info("Initializing Kubernetes client...")

            # Load Kubernetes configuration
            config_mode = self.config.get("k8s", {}).get("config_mode", "local")
            if config_mode == "local":
                logger.debug("Loading kubeconfig for local setup.")
                config.load_kube_config()
            elif config_mode == "in-cluster":
                logger.debug("Loading in-cluster Kubernetes configuration.")
                config.load_incluster_config()
            else:
                logger.error(f"Invalid config_mode: {config_mode}")
                raise ValueError(f"Invalid config_mode: {config_mode}. Use 'local' or 'in-cluster'.")

            # Get proxy configuration from the settings
            http_proxy = self.config.get("proxy", {}).get("http_proxy")
            https_proxy = self.config.get("proxy", {}).get("https_proxy")
            verify_ssl = self.config.get("proxy", {}).get("verify_ssl", False)

            # Get the default Kubernetes configuration
            self.k8s_config = Configuration.get_default_copy()

            # explicitly set the CA certificate from kubeconfig
            logger.info(f"Using CA certificate: { self.k8s_config.ssl_ca_cert}")

            # Configure SSL verification
            self.k8s_config.verify_ssl = True
            logger.info(f"SSL verification set to: {verify_ssl}")

            # Initialize the ApiClient with the configuration
            self.api_client = ApiClient(configuration = self.k8s_config)

            # Set the proxy in the ApiClient if provided
            if http_proxy:
                logger.info(f"Configuring HTTPS proxy: {https_proxy}")
                self.api_client.rest_client.pool_manager = urllib3.ProxyManager(
                    proxy_url = https_proxy,
                    cert_reqs = "CERT_REQUIRED" if verify_ssl else "CERT_NONE",
                )
            elif http_proxy:
                logger.info(f"Configuring HTTP proxy: {http_proxy}")
                self.api_client.rest_client.pool_manager = urllib3.ProxyManager(
                    proxy_url = http_proxy,
                    cert_reqs = "CERT_REQUIRED" if verify_ssl else "CERT_NONE",
                )

            # Initialize the Kubernetes API client
            # self.client = client.AppsV1Api(api_client)
            logger.info("Kubernetes client initialized successfully")

        except Exception as e:
            logger.exception(f"Failed to initialize Kubernetes client: {e}")
            raise

    def get_client(self, api_type):
        """
        Retrieve the specified Kubernetes API client.

        Args:
            api_type (str): Type of Kubernetes API client (e.g., "AppsV1Api", "CoreV1Api").

        Returns:
            object: The requested Kubernetes API client instance.
        """
        if api_type not in self.api_clients:
            logger.info(f"Initializing API client for: {api_type}")
            if api_type == "AppsV1Api":
                self.api_clients[api_type] = client.AppsV1Api(self.api_client)
            elif api_type == "CoreV1Api":
                self.api_clients[api_type] = client.CoreV1Api(self.api_client)
            else:
                logger.error(f"Unsupported API client type: {api_type}")
                raise ValueError(f"Unsupported API client type: {api_type}")
        return self.api_clients[api_type]