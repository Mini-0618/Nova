import json

with open('config.json') as f:
    config = json.load(f)

greeting = config['greeting']
max_retries = config['max_retries']
print(f'{greeting}! Will retry {max_retries} times')