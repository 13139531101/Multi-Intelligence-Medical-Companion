import requests
import json
import time
import os

# Config
API_URL = "http://127.0.0.1:13002"
USERNAME = "test_user_routing"
PASSWORD = "password123"

def get_auth_token():
    print(f"\nAuthenticating as {USERNAME}...")

    # Try login first
    login_data = {
        "username": USERNAME,
        "password": PASSWORD
    }

    try:
        resp = requests.post(f"{API_URL}/auth/login", json=login_data)
        if resp.status_code == 200:
            print("Login successful!")
            return resp.json()["access_token"]

        print(f"Login failed ({resp.status_code}), trying registration...")

        # Try register
        register_data = {
            "username": USERNAME,
            "password": PASSWORD,
            "email": f"{USERNAME}@example.com"
        }
        resp = requests.post(f"{API_URL}/auth/register", json=register_data)
        if resp.status_code == 200:
            print("Registration successful!")
            return resp.json()["access_token"]

        print(f"Registration failed: {resp.text}")
        return None

    except Exception as e:
        print(f"Auth request failed: {e}")
        return None

def run_routing(token):
    print("\nTesting Agent Routing...")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    # We rely on the metadata in the JSON body, which is the primary way.
    # The header was added as a fallback/force mechanism, but Python requests doesn't like non-ASCII headers.

    # 1. Create Conversation
    print("Creating conversation...")
    try:
        resp = requests.post(f"{API_URL}/conversation/create", headers=headers)
        if resp.status_code != 200:
            print(f"Failed to create conversation: {resp.text}")
            return

        conv_data = resp.json()
        conversation_id = conv_data['result']['conversation_id']
        print(f"Conversation created: {conversation_id}")

        # 2. Send Message to Health Advisor
        print("Sending message to Health Advisor...")
        message = {
            "params": {
                "role": "user",
                "parts": [{"type": "text", "text": "你好，我最近头痛，有什么建议吗？"}],
                "metadata": {
                    "conversation_id": conversation_id,
                    "selected_agent": "健康顾问" # Also put in metadata as backup
                }
            }
        }

        # Note: The frontend uses /message/send which is async and returns immediately usually
        # But we need to check if we get a response eventually.
        # In this system, /message/send triggers a background task.
        # We need to poll /message/list or /events/get to see the response.

        # Ensure proper encoding for the request body
        import json
        resp = requests.post(
            f"{API_URL}/message/send",
            data=json.dumps(message).encode('utf-8'),
            headers=headers
        )
        if resp.status_code != 200:
            print(f"Failed to send message: {resp.text}")
            return

        print("Message sent successfully. Waiting for response...")

        # 3. Poll for response
        max_retries = 30
        for i in range(max_retries):
            print(f"Polling attempt {i+1}/{max_retries}...")

            # Check message list
            list_req = {
                "params": {
                    "conversation_id": conversation_id
                }
            }
            resp = requests.post(f"{API_URL}/message/list", json=list_req, headers=headers)

            if resp.status_code == 200:
                data = resp.json()
                if 'result' in data:
                    msgs = data['result']
                else:
                    msgs = data # In case it returns list directly (unlikely but safe)

                # msgs is a list of messages
                # We expect at least 2 messages: user's input and agent's response
                if len(msgs) >= 2:
                    last_msg = msgs[-1]
                    if last_msg.get('role') == 'model' or last_msg.get('role') == 'agent':
                        print(f"Received response from agent: {last_msg.get('parts')[0].get('text')[:50]}...")
                        return

            time.sleep(2)

        print("Timed out waiting for agent response.")

    except Exception as e:
        print(f"Test failed: {e}")

if __name__ == "__main__":
    token = get_auth_token()
    if token:
        run_routing(token)
