import requests
import json
import time
import os

API_URL = "http://localhost:13002"

def test_heuristic_routing():
    print("=== Testing Heuristic Routing ===")

    # 1. Login/Register
    print("\n1. Authenticating...")
    auth_payload = {
        "username": "test_user_heuristic",
        "password": "password123",
        "email": "heuristic@example.com"
    }

    # Try login first
    print("Trying login...")
    resp = requests.post(f"{API_URL}/auth/login", json=auth_payload)
    if resp.status_code != 200:
        # Register if login fails
        print("Login failed, trying registration...")
        reg_resp = requests.post(f"{API_URL}/auth/register", json=auth_payload)
        if reg_resp.status_code == 200:
            print("Registration successful, logging in...")
            resp = requests.post(f"{API_URL}/auth/login", json=auth_payload)
        else:
            print(f"Registration failed: {reg_resp.text}")
            return

    if resp.status_code != 200:
        print(f"Authentication failed: {resp.text}")
        return

    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Authentication successful.")

    # 2. Create Conversation
    print("\n2. Creating Conversation...")
    resp = requests.post(f"{API_URL}/conversation/create", headers=headers)
    if resp.status_code != 200:
        print(f"Failed to create conversation: {resp.text}")
        return

    response_json = resp.json()
    if "result" in response_json and "conversation_id" in response_json["result"]:
        conversation_id = response_json["result"]["conversation_id"]
    else:
        print(f"Unexpected response format: {json.dumps(response_json, indent=2)}")
        return

    print(f"Conversation ID: {conversation_id}")

    # 3. Send Message (Without selected_agent)
    print("\n3. Sending Message '我头疼' (No explicit agent selected)...")
    message_payload = {
        "params": {
            "role": "user",
            "parts": [{"text": "我头疼", "type": "text"}],
            "metadata": {
                "conversation_id": conversation_id,
                # "selected_agent": ""  <-- INTENTIONALLY OMITTED
            }
        }
    }

    resp = requests.post(f"{API_URL}/message/send", json=message_payload, headers=headers)
    if resp.status_code != 200:
        print(f"Failed to send message: {resp.text}")
        return
    print("Message sent successfully.")

    # 4. Poll for Response
    print("\n4. Polling for Response...")
    for i in range(30):  # Increase to 30 attempts (60 seconds)
        print(f"Polling attempt {i+1}/30...")
        try:
            resp = requests.post(f"{API_URL}/message/list", json={"params": {"conversation_id": conversation_id}}, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                # Try to get messages from 'result' (standard) or 'messages' (legacy/alternative)
                messages = data.get("result", data.get("messages", []))

                print(f"DEBUG: Received {len(messages)} messages.")
                if messages:
                    last_msg = messages[-1]
                    print(f"DEBUG: Last message role: {last_msg.get('role')}")
                    if last_msg.get("role") == "agent":
                        print("\nSUCCESS: Received response from agent!")
                        print("Response content:", json.dumps(last_msg, indent=2, ensure_ascii=False))
                        return
            else:
                print(f"Polling failed with status {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"Polling error: {e}")

        time.sleep(2)

    print("\nFAILURE: No response received after polling.")

if __name__ == "__main__":
    test_heuristic_routing()
