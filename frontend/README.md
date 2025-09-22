# Single Agent and Multi-Agent Frontend

📘 [中文Readme](./README_ZH.md)

This project demonstrates how multiple A2A Agents collaborate to complete tasks, including multiple Agent backend services, a unified orchestration interface, and a frontend interface. It supports both single and multi-Agent modes.

## 📁 Project Structure
* **hostAgentAPI**: Central API for coordinating multiple Agents, determining which Agent to call, checking status, etc.
* **multiagent_front**: Frontend interface for multi-Agent collaboration mode
* **single_agent**: Frontend interface for single-Agent mode

## 🚀 Quick Start
### 1. Multi-Agent Mode

#### 1. Start an A2A Agent
Start Agent RAG:
```
cd backend/AgentRAG
python main.py --port 10005
```

#### 2. Start a Second Agent, DeepSearch
```
cd backend/DeepSearch
python main.py --port 10004
```

#### 3. Start the Host Agent for Coordinating Multiple Agents
The host Agent decides which Agent to use and monitors their status:
```
cd hostAgentAPI
pip install -r requirements.txt
python api.py
```

#### 4. Start the Frontend
```
cd multiagent_front
npm install
npm run dev
```

#### 5. Add Agent Configurations and Start Q&A in the Web Interface
After opening the frontend page, add the addresses and information for each Agent.  
Input a question and observe the collaborative response process of multiple Agents.

### 2. Single A2A Mode

#### 1. Start an A2A Agent, e.g., Agent RAG
```
cd backend/AgentRAG
python main.py --port 10005
```

#### 2. Start the Frontend
```
cd single_agent
npm install
npm run dev
```

#### 3. Open the Frontend Page and Start Q&A
Open the frontend page, input the URL address of the Agent to use, and begin the Q&A session.

## 💡 Project Highlights
- Multi-Agent orchestration and collaboration framework, easily extensible for integrating additional intelligent Agents
- Separated frontend and backend with a clear interface, supporting dynamic Agent addition
- Supports isolated testing of individual Agent capabilities and performance

## 📌 Notes
- All services run locally by default; ensure the ports are not occupied.