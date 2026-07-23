import httpx
r = httpx.get('http://localhost:5174/src/pages/HealthRecords.jsx', timeout=10)
text = r.text
print('ocr-progress-banner:', 'ocr-progress-banner' in text)
print('position fixed:', '"fixed"' in text)
print('zIndex 1400:', '1400' in text)
print('banner-box:', 'Box$' in text or 'data-testid' in text)
print('len:', len(text))
