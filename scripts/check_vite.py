import httpx
r = httpx.get('http://localhost:5174/src/pages/HealthRecords.jsx', timeout=10)
print(f'status: {r.status_code}, len: {len(r.text)}')
text = r.text
print('ocr-progress-banner in JS:', 'ocr-progress-banner' in text)
print('filesNorm in JS:', 'filesNorm' in text)
print('正在识别 in JS:', '正在识别' in text)
print('---count of data-testid banner matches:', text.count('data-testid'))

