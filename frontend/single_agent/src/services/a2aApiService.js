import { v4 as uuidv4 } from 'uuid';
import { fetchEventSource } from '@microsoft/fetch-event-source';

const AGENT_CARD_PATH = "/.well-known/agent.json";

export async function getAgentCard(baseUrl) {
  const url = `${baseUrl.replace(/\/$/, "")}${AGENT_CARD_PATH}`;
  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`HTTP error ${response.status}: ${response.statusText}`);
    }
    const cardData = await response.json();
    // Add the agent's base URL to the card for later use, as the card's `url` field is the specific endpoint
    return { ...cardData, agentBaseUrl: baseUrl, agentEndpointUrl: cardData.url };
  } catch (error) {
    console.error("Error fetching agent card:", error);
    throw error;
  }
}

export async function sendTaskNonStreaming(agentEndpointUrl, payload) {
  const requestBody = {
    jsonrpc: "2.0",
    method: "tasks/send",
    params: payload,
    id: uuidv4(),
  };

  try {
    const response = await fetch(agentEndpointUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody),
      timeout: 30000, // 30 seconds timeout
    });

    if (!response.ok) {
      const errorData = await response.text();
      throw new Error(`HTTP error ${response.status}: ${errorData}`);
    }
    return await response.json();
  } catch (error) {
    console.error("Error sending non-streaming task:", error);
    throw error;
  }
}

export async function getTaskResult(agentEndpointUrl, taskId) {
  const requestBody = {
    jsonrpc: "2.0",
    method: "tasks/get",
    params: { id: taskId },
    id: uuidv4(),
  };

  try {
    const response = await fetch(agentEndpointUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      const errorData = await response.text();
      throw new Error(`HTTP error ${response.status}: ${errorData}`);
    }
    return await response.json();
  } catch (error) {
    console.error("Error getting task result:", error);
    throw error;
  }
}

export function sendTaskStreaming(agentEndpointUrl, payload, onMessage, onError, onClose) {
  const requestBody = {
    jsonrpc: "2.0",
    method: "tasks/sendSubscribe", // Matches Python client for streaming
    params: payload,
    id: uuidv4(),
  };

  // The @microsoft/fetch-event-source library is used here
  // It's more robust than a raw EventSource or fetch for SSE
  const ctrl = new AbortController();

  fetchEventSource(agentEndpointUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    },
    body: JSON.stringify(requestBody),
    signal: ctrl.signal,
    openWhenHidden: true, // Continue if tab is not active
    async onopen(response) {
      if (response.ok && response.headers.get('content-type')?.includes('text/event-stream')) {
        console.log("SSE Connection opened");
      } else {
        const errorText = await response.text();
        console.error(`Failed to connect to SSE: ${response.status} ${response.statusText}`, errorText);
        onError(new Error(`Failed to connect to SSE: ${response.status} ${errorText}`));
        ctrl.abort(); // Abort if not a valid SSE stream
      }
    },
    onmessage(event) {
      // Assuming the server sends data in the 'data' field of the SSE event
      // And that data is a JSON string representing the TaskStatusUpdateEvent or TaskArtifactUpdateEvent
      console.log("Raw SSE event:", event.data);
      if (!event.data?.trim()) {
        // 忽略空数据或心跳
        return;
      }
      try {
        const parsedData = JSON.parse(event.data);
        onMessage(parsedData);
      } catch (e) {
        console.error("Failed to parse SSE message data:", e, "Raw data:", event.data);
        onError(e);
      }
    },
    onclose() {
      console.log("SSE Connection closed.");
      if (onClose) {
        onClose();
      }
    },
    onerror(err) {
      console.error("SSE Error:", err);
      onError(err);
      // The library handles retries. If it's a fatal error or retries are exhausted,
      // it will throw, which should be caught by the caller or handled here.
      // Depending on the error, you might want to abort:
      // if (err.status === 401 || err.status === 403) ctrl.abort();
      throw err; // Propagate to stop retries by default for unknown errors
    }
  });

  return () => {
    console.log("Aborting SSE stream");
    ctrl.abort();
  };
}