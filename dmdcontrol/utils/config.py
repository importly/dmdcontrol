"""Loads configuration file."""

import yaml
from pathlib import Path
from .env import WORKSPACE

CONFIG_PATH = WORKSPACE / "config.yaml"


def load_config() -> dict:
    """
    Loads the configuration file and returns it as a dictionary.

    Returns:
        dict: The configuration as a dictionary.
    """
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)
    
CONFIG = load_config()