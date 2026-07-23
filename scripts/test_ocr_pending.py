"""Simulates user upload flow: upload PNG + create record with attached_file_id, then check OCR pending status"""
import httpx, time, json
tok = httpx.post('http://localhost:13002/auth/login', json={'username':'1111','password':'111111'}, timeout=10).json()['access_token']
USER = 'user_4e3ef0b3f49d8d4433e0b4420a3bae2a'
HEADERS = {'Authorization': 'Bearer '+tok, 'Idempotency-Key': f'ocr-test-{int(time.time())}'}

# 1. Upload a real 1x1 png
PNG_BYTES = (
    b'\x89PNG\r\n\x1a\n'                                    # magic
    b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'    # 1x1 header
    b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'                   # depth, etc
    b'\x00\x00\x00\rIDATx\x9cc\xfc\xcf\xc0\x00\x00\x00\x03\x00\x01\x5c\xcd\xff'
    b'\x69\x00\x00\x00\x00IEND\xaeB`\x82'                     # end
)
print(f'PNG size: {len(PNG_BYTES)} bytes')

r = httpx.post('http://localhost:13002/v2/upload/file',
               data={'user_id': USER, 'domain': 'pha', 'purpose': 'health_record', 'limit': 10},
               files={'file': ('test.png', PNG_BYTES, 'image/png')},
               headers={'Authorization': 'Bearer '+tok}, timeout=20)
print('upload status:', r.status_code)
fid = r.json()['file_id']
ocr_status = r.json()['ocr_status']
print(f'file_id={fid}, ocr_status={ocr_status}')

# 2. Wait 2s and check ocr status
time.sleep(2)
r2 = httpx.get(f'http://localhost:13002/v2/upload/file/{fid}?user_id={USER}',
               headers={'Authorization': 'Bearer '+tok}, timeout=10)
print(f'GET file after 2s: {r2.status_code} status={r2.json().get("ocr_status")} text_len={len(r2.json().get("ocr_text") or "")}')
