# Host Agent API
📘 [中文Readme](./README_ZH.md)

The coordinator and organizer Agent startup interface for A2A.

# Getting Started

**Project Overview:**

The goal of this project is to provide API interfaces for the coordinator and organizer agents of A2A to enable startup and management functionalities. Through these interfaces, seamless interaction with other agents can be achieved, thereby facilitating control over other agents.
**Quick Start:**

1.  **Environment Setup:**
    * Ensure you have Python 3 installed on your system.
    * (If the project has dependencies) Install the required packages using pip:
        ```bash
        pip install -r requirements.txt
        ```
        *Note: Execute this step if your project has a `requirements.txt` file. Otherwise, you can skip it.*

2.  **Start the API Service:**
    * Navigate to the project's root directory and run the following command to start the API service:
        ```bash
        python api.py
        ```
    * By default, the API service might start on a local address and port (e.g., `http://localhost:13000`). 

**API Interface Testing:**

The project includes a `test_api.py` script to test the functionality of each API endpoint. This script utilizes the `unittest` framework to send requests to each endpoint and verify the responses.

1.  **Run the Test Script:**
    * Ensure the API service is running successfully (see the "Start the API Service" step above).
    * In the project's root directory, execute the test script:
        ```bash
        python test_api.py
        ```
    * The test script will automatically run all test cases and output the test results for each endpoint, including status codes, response content, and execution time, helping you verify the API's usability.

**API Endpoint Documentation:**

The following are the API endpoints and their functionalities, analyzed from the `test_api.py` file:

* **`/ping` (GET)**
    * **Functionality:** Tests if the API service is running and healthy.
    * **Request Example:** `GET http://127.0.0.1:13000/ping`
    * **Response Example:** `"Pong"`

* **`/conversation/create` (POST)**
    * **Functionality:** Creates a new conversation.
    * **Request Body:** None
    * **Response Example:**
        ```json
        {
          "result": {
            "conversation_id": "unique_conversation_id_generated"
          }
        }
        ```

* **`/conversation/list` (POST)**
    * **Functionality:** Lists all current conversations.
    * **Request Body:** None
    * **Response Example:**
        ```json
        {
          "result": [
            "conversation_id_1",
            "conversation_id_2",
            ...
          ]
        }
        ```

* **`/message/send` (POST)**
    * **Functionality:** Sends a message to a specified conversation.
    * **Request Body (application/json):**
        ```json
        {
          "params": {
            "role": "user",
            "parts": [{"type": "text", "text": "Message content to send"}],
            "metadata": {"conversation_id": "target_conversation_id"}
          }
        }
        ```
    * **Response Example:**
        ```json
        {
          "result": {
            "message_id": "generated_message_id",
            "conversation_id": "corresponding_conversation_id"
          }
        }
        ```

* **`/message/list` (POST)**
    * **Functionality:** Lists all messages within a specified conversation.
    * **Request Body (application/json):**
        ```json
        {
          "params": "target_conversation_id"
        }
        ```
    * **Response Example:**
        ```json
        {
          "result": [
            {
              "metadata": {"message_id": "message_id_1", ...},
              "role": "user",
              "parts": [{"type": "text", "text": "message_content_1"}]
            },
            {
              "metadata": {"message_id": "message_id_2", ...},
              "role": "assistant",
              "parts": [{"type": "text", "text": "reply_content_1"}]
            },
            ...
          ]
        }
        ```

* **`/message/pending` (POST)**
    * **Functionality:** Retrieves messages that are currently being processed (pending).
    * **Request Body:** None
    * **Response Example:**
        ```json
        {
          "result": [
            ["conversation_id_1", "message_id_1"],
            ["conversation_id_2", "message_id_2"],
            ...
          ]
        }
        ```
        *Note: An empty `result` array indicates that there are no messages currently pending.*

* **`/events/get` (POST)**
    * **Functionality:** Retrieves a list of events that have occurred (e.g., new message events).
    * **Request Body:** None
    * **Response Example:**
        ```json
        {
          "result": [
            {"event_type": "new_message", "data": {...}},
            ...
          ]
        }
        ```
        *Note: The `result` may contain event information when new questions or interactions occur.*

* **`/task/list` (POST)**
    * **Functionality:** Lists the current tasks.
    * **Request Body:** None
    * **Response Example:**
        ```json
        {
          "result": [
            {"task_id": "task_id_1", "status": "running", ...},
            ...
          ]
        }
        ```

* **`/agent/register` (POST)**
    * **Functionality:** Registers a new Agent.
    * **Request Body (application/json):**
        ```json
        {
          "params": "URL address of the Agent (e.g., 127.0.0.1:10003)"
        }
        ```
    * **Response Example:**
        ```json
        {
          "result": "registration_result_information"
        }
        ```

* **`/agent/list` (POST)**
    * **Functionality:** Lists all registered Agents.
    * **Request Body:** None
    * **Response Example:**
        ```json
        {
          "result": ["agent_url_1", "agent_url_2", ...]
        }
        ```

* **`/api_key/update` (POST)**
    * **Functionality:** Updates the API Key.
    * **Request Body (application/json):**
        ```json
        {
          "api_key": "new_api_key"
        }
        ```
    * **Response Example:**
        ```json
        {
          "status": "success"
        }
        ```
