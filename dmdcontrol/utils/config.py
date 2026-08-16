"""Loads configuration file."""

import yaml
from pathlib import Path
from .env import WORKSPACE

CONFIG_PATH = WORKSPACE / "config.yaml"


def validate_config(config: dict) -> bool:
    """
    Validates the config file values

    Args:
        config (dict): configuration dictionary to validate

    Returns:
        bool: whether it's valid or not
    """
    
    if config.get('DMD', {}).get('target_hz', 1.0) <= 0:
        return False
    
    if config.get('DMD', {}).get('dark_time_us', 0) < 0:
        return False
    
    if config.get('DMD', {}).get('frame_utilization', 1.0) <= 0.0 or config.get('DMD', {}).get('frame_utilization', 1.0) > 1.0:
            return False

    if config.get('DMD', {}).get('exposure_us', 0) < config.get('DMD', {}).get('min_exposure_us', 0):
                return False

    return True


def load_config() -> dict:
    """
    Loads the configuration file and returns it as a dictionary.

    Returns:
        dict: The configuration as a dictionary.
    """
    with open(CONFIG_PATH, 'r') as f:
        config =  yaml.safe_load(f)
        
    if not validate_config(config):
        raise ValueError('Invalid configuration values in config.yaml')
    
    return config


CONFIG = load_config()