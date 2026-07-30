"""Test what the browser gets and see if /src/main.jsx imports resolve"""
import httpx
# Look at the resolved main.jsx imports
r = httpx.get('http://localhost:5174/src/main.jsx', timeout=8)
text = r.text
import re
# Find all import URLs
imports = re.findall(r'import.*?from "(/[^"]+)"', text)
print('Imports from main.jsx:')
for u in imports[:10]:
    print(' ', u)

# Check the key ones
for u in ['/@id/__x00__react/jsx-dev-runtime',
           '/node_modules/.vite/deps/react.js',
           '/src/App.jsx']:
    if u in text:
        print(f'  - {u} ... present')

# Test each import
print('\n--- Resolve each ---')
for u in imports[:5]:
    try:
        r2 = httpx.get(f'http://localhost:5174{u}', timeout=8)
        print(f'  {u} -> {r2.status_code} (len {len(r2.text)})')
    except Exception as e:
        print(f'  {u} -> ERR {e}')