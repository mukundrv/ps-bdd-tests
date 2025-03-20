import tomli
import logging
from src.utils.logging_util import get_logger

logger = get_logger(__name__)

def load_config(config_file="config/settings.toml"):
    """
    Load configuration from a TOML file.

    Args:
        config_file (str): Path to the configuration file.

    Returns:
        dict: Parsed configuration data.
    """
    logger.info(f"Loading configuration from {config_file}...")
    try:
        with open(config_file, "rb") as file:
            config = tomli.load(file)
        logger.info("Configuration loaded successfully.")
        return config
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise