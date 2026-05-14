
import requests

try:
    response = requests.get('http://127.0.0.1:11434/api/tags')
    if response.status_code == 200:
        models = response.json().get('models', [])
        print("Available models:")
        for m in models:
            print(f"- {m['name']}")
    else:
        print(f"Error fetching models: {response.status_code}")
except Exception as e:
    print(f"Connection error: {e}")
