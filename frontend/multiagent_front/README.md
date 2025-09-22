# A2A Multi-Agent Conversation Frontend
📘 [中文Readme](./README_ZH.md)

This application provides a user interface for interacting with an A2A (Agent-to-Agent) multi-agent system.

## Quick Start

Follow these steps to run this frontend application locally:

### Prerequisites

Ensure you have Node.js and npm (or yarn) installed.

### Install Dependencies

Execute the following command in the project's root directory to install the required dependencies:

```bash
npm install
```

### Configure Environment Variables
Check the .env file in the project's root directory.
Confirm that the value of the REACT_APP_HOSTAGENT_API environment variable matches the port of your HostAgentAPI service.  For example:
```
REACT_APP_HOSTAGENT_API=http://127.0.0.1:13000
```
If your HostAgentAPI service is running on a different address or port, please modify the .env file accordingly.

### Start the Application
Execute the following command to start the development server:
```bash
npm run dev
```
Once started successfully, your browser should automatically open the application. If it doesn't open automatically, please visit the address displayed in the console (usually http://localhost:5173 or another address).