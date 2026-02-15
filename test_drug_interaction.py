import requests
import json
import uuid

url = "http://localhost:10012/"
headers = {"Content-Type": "application/json"}

payload = {
    "jsonrpc": "2.0",
    "method": "tasks/send",
    "params": {
        "id": str(uuid.uuid4()),
        "sessionId": str(uuid.uuid4()),
        "message": {
            "role": "user",
            "parts": [{"type": "text", "text": "Check interactions between Aspirin and my current medications. My user_id is test-123."}]
        }
    },
    "id": 1
}

try:
    print(f"Sending request to {url}...")
    response = requests.post(url, json=payload, headers=headers, timeout=600) # Long timeout for debug
    print(f"Status Code: {response.status_code}")
    print("Response:")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
except Exception as e:
    print(f"Error: {e}")
