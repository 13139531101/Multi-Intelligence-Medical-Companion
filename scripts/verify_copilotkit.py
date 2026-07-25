"""Verify CopilotKit integration"""
import httpx
r = httpx.get('http://localhost:5174/src/App.jsx', timeout=8)
text = r.text
print('vite status:', r.status_code, ', len:', len(text))
print('has @copilotkit/react-core:', '@copilotkit/react-core' in text)
print('has CopilotPopup:', 'CopilotPopup' in text)
print('has </CopilotKit>:', '</CopilotKit>' in text)

r2 = httpx.get('http://localhost:5174/api/copilotkit', timeout=5)
print('vite proxy /api/copilotkit:', r2.status_code)
print('proxy response sample:', r2.text[:200])

r3 = httpx.get('http://localhost:5174/health', timeout=5)
print('vite proxy /health:', r3.status_code)