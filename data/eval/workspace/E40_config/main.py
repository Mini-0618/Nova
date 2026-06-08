#!/usr/bin/env python3
"""E40: Config file support."""
import json
import os

config_path = os.path.join(os.path.dirname(__file__), 'config.json')
with open(config_path, 'r') as f:
    config = json.load(f)

greeting = config.get('greeting', 'Hello')
max_retries = config.get('max_retries', 5)
print(f'{greeting}! Will retry {max_retries} times')
