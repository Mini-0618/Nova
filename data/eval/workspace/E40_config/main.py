import json
import os

def load_config(config_path=None):
    """Load configuration from a JSON file."""
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Error: Config file '{config_path}' not found.")
        raise
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file '{config_path}': {e}")
        raise

    # Validate required keys
    required_keys = ["greeting", "max_retries"]
    missing = [k for k in required_keys if k not in config]
    if missing:
        print(f"Error: Missing required config keys: {missing}")
        raise KeyError(f"Missing required config keys: {missing}")

    return config

if __name__ == "__main__":
    config = load_config()
    greeting = config["greeting"]
    max_retries = config["max_retries"]
    print(f'{greeting}! Will retry {max_retries} times')