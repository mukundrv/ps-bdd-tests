import logging
import tomli  # For parsing TOML configuration files


def load_logging_config(config_file="config/settings.toml"):
    """
    Load the logging configuration from a TOML file.

    Args:
        config_file (str): Path to the configuration file.

    Returns:
        str: The log level specified in the configuration file.
    """
    try:
        with open(config_file, "rb") as file:
            config = tomli.load(file)
        return config.get("logging", {}).get("level", "INFO")  # Default to INFO
    except Exception as e:
        print(f"Failed to load logging configuration: {e}")
        return "INFO"  # Fallback to INFO if config fails


def get_logger(name: str, config_file="config/settings.toml"):
    """
    Returns a logger instance with a consistent format.

    Args:
        name (str): The name of the logger.
        config_file (str): Path to the configuration file.

    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(name)
    if not logger.hasHandlers():
        # Load log level from configuration
        log_level_str = load_logging_config(config_file)
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)

        # Set logging level and format
        logger.setLevel(log_level)
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    return logger
