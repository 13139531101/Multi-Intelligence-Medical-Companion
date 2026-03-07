import requests
import json
import uuid
import time

# Config
API_URL = "http://127.0.0.1:13002"  # hostapi port (updated)


def get_auth_token(username="test_user", password="password123"):
    print(f"\nAuthenticating as {username}...")

    # Try login first
    login_data = {
        "username": username,
        "password": password
    }

    try:
        resp = requests.post(f"{API_URL}/auth/login", json=login_data)
        if resp.status_code == 200:
            print("Login successful!")
            return resp.json()["access_token"]

        print(f"Login failed ({resp.status_code}), trying registration...")

        # Try register
        register_data = {
            "username": username,
            "password": password,
            "email": f"{username}@example.com"
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


def test_history_api():
    token = get_auth_token()
    if not token:
        print("Failed to get auth token, aborting test.")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    print(f"Target API: {API_URL}")
    print(f"Using token: {token[:20]}...")

    # 1. Create Consultation
    print("\n1. Creating Consultation...")
    cid = uuid.uuid4().hex
    create_payload = {
        "consultation_id": cid,
        "question": "测试历史记录功能",
        "session_id": uuid.uuid4().hex,
        "tags": ["test", "debug"]
    }
    try:
        resp = requests.post(f"{API_URL}/api/consultations/create", json=create_payload, headers=headers)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")
        if resp.status_code != 200:
            print("Failed to create consultation")
            return
    except Exception as e:
        print(f"Request failed: {e}")
        return

    # 2. Save User Message
    print("\n2. Saving User Message...")
    msg_content = "这是一条测试消息"
    save_payload = {
        "consultation_id": cid,
        "role": "user",
        "content": msg_content,
        "files": ["http://example.com/file1.jpg"]  # Test files support
    }
    try:
        resp = requests.post(f"{API_URL}/api/consultations/message", json=save_payload, headers=headers)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")
        if resp.status_code != 200:
            print("Failed to save message")
            return
    except Exception as e:
        print(f"Request failed: {e}")
        return

    # 3. Get Messages
    print("\n3. Getting Messages...")
    # Wait a bit to ensure DB consistency (though strict consistency should be immediate)
    time.sleep(1)
    try:
        resp = requests.get(f"{API_URL}/api/consultations/{cid}/messages", headers=headers)
        print(f"Status: {resp.status_code}")
        # print(f"Response: {resp.text}")

        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                msgs = data.get("messages", [])
                print(f"Found {len(msgs)} messages")
                found = False
                for m in msgs:
                    print(f" - [{m['role']}] {m['content']} (Files: {m.get('files')})")
                    if m['content'] == msg_content:
                        found = True

                if found:
                    print("\nSUCCESS: Message verified in history!")
                else:
                    print("\nFAILURE: Message not found in history.")
            else:
                print(f"API returned success=False: {data}")
        else:
            print("Failed to get messages")

    except Exception as e:
        print(f"Request failed: {e}")

    # 4. Get History List
    print("\n4. Getting Consultation History List...")
    try:
        resp = requests.get(f"{API_URL}/api/consultations/history?limit=5", headers=headers)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            history = resp.json()
            print(f"Found {len(history)} history records")
            found_cid = False
            for h in history:
                print(f" - ID: {h.get('consultation_id')} Title: {h.get('title')} Tags: {h.get('tags')}")
                if h.get('consultation_id') == cid:
                    found_cid = True

            if found_cid:
                print("\nSUCCESS: Consultation found in history list!")
            else:
                print("\nFAILURE: Consultation not found in history list.")
        else:
            print(f"Failed to get history list: {resp.text}")
    except Exception as e:
        print(f"Request failed: {e}")
        return

    # 3. Get Messages
    print("\n3. Fetching Messages...")
    try:
        resp = requests.get(f"{API_URL}/api/consultations/{cid}/messages", headers=headers)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Response: {json.dumps(data, ensure_ascii=False, indent=2)}")
            messages = data.get("messages", [])
            if len(messages) > 0:
                print("Messages found!")
                if "files" in messages[0]:
                    print(f"Files found: {messages[0]['files']}")
            else:
                print("No messages found in DB!")
        else:
            print(f"Failed to fetch messages: {resp.text}")
    except Exception as e:
        print(f"Request failed: {e}")


if __name__ == "__main__":
    test_history_api()
