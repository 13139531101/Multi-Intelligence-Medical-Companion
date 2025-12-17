import requests
import json
import uuid
import time

AGENT_URL = "http://127.0.0.1:10011"

def test_streaming():
    url = AGENT_URL

    # Simulate a user message that triggers the diagnosis tool
    payload = {
        "jsonrpc": "2.0",
        "method": "tasks/sendSubscribe",
        "params": {
            "id": uuid.uuid4().hex,
            "sessionId": uuid.uuid4().hex,
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "我头痛，发烧，请帮我诊断"}]
            }
        },
        "id": f"req_{uuid.uuid4().hex}"
    }

    print(f"Sending request to {url}...")

    try:
        response = requests.post(url, json=payload, stream=True, timeout=60)
        print(f"Response status: {response.status_code}")

        if response.status_code != 200:
            print(response.text)
            return

        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith("data: "):
                    data_str = decoded_line[6:].strip()
                    if data_str == "[DONE]":
                        print("\n[Stream finished]")
                        break

                    try:
                        data = json.loads(data_str)
                        # Extract content
                        content = ""
                        if "result" in data:
                            res = data["result"]
                            # Check for tool calls or normal text
                            if "artifact" in res:
                                # This is usually final answer or thought
                                for p in res["artifact"].get("parts", []):
                                    if p["type"] == "text":
                                        content += p["text"]
                            elif "message" in res:
                                 # Intermediate messages
                                 for p in res["message"].get("parts", []):
                                    if p["type"] == "text":
                                        content += p["text"]
                            elif "status" in res and "message" in res["status"]:
                                 # Status updates
                                 for p in res["status"]["message"].get("parts", []):
                                    if p["type"] == "text":
                                        content += p["text"]

                        if content:
                            print(content, end="", flush=True)
                    except Exception as e:
                        print(f"\n[Error parsing]: {e}")

    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    # Wait a bit for server to fully start if we just launched it
    time.sleep(5)
    test_streaming()
