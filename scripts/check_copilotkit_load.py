"""Check CopilotKit module loads"""
import httpx

# Try the deps file vite generated for @copilotkit/react-core
for url in [
    '/node_modules/.vite/deps/@copilotkit_react-core.js',
    '/node_modules/.vite/deps/@copilotkit_react-ui.js',
]:
    try:
        r = httpx.get(f'http://localhost:5174{url}', timeout=8)
        print(f'{url} -> {r.status_code} (len {len(r.text)})')
        # Find what's in it
        if r.status_code != 200 or len(r.text) < 200:
            print('  body sample:', r.text[:300])
    except Exception as e:
        print(f'{url} -> ERR {e}')

# Read vite-5174.err.log
print('\n--- vite-5174.err.log ---')
with open(r'I:\A2A\3\A2AServer\frontend\multiagent_front\vite-5174.err.log', 'r', errors='ignore') as f:
    print(f.read()[:2000])

print('\n--- vite-5174.log (last 1500 chars) ---')
with open(r'I:\A2A\3\A2AServer\frontend\multiagent_front\vite-5174.log', 'r', errors='ignore') as f:
    text = f.read()
    print(text[-1500:])