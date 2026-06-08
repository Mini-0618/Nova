import json
import os

config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
try:
    with open(config_path) as f:
        config = json.load(f)
except FileNotFoundError:
    config = {}

greeting = config.get('greeting', 'Hello')
max_retries = config.get('max_retries', 5)
print(f'{greeting}! Will retry {max_retries} times')
