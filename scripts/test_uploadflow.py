"""Simulate full user flow + check records[0].files[0].ocr_status right after creating"""
import httpx, time
tok = httpx.post('http://localhost:13002/auth/login', json={'username':'1111','password':'111111'}, timeout=10).json()['access_token']
USER = 'user_4e3ef0b3f49d8d4433e0b4420a3bae2a'

# upload big-ish image to slow OCR
big = b'\x89PNG\r\n\x1a\n' + b'\x00' * 200000  # ~200KB pretend PNG

# 1) upload
r = httpx.post('http://localhost:13002/v2/upload/file',
               data={'user_id': USER, 'domain': 'pha', 'purpose': 'health_record', 'limit': 10},
               files={'file': ('big.png', big, 'image/png')},
               headers={'Authorization': 'Bearer '+tok}, timeout=30)
fid = r.json()['file_id']
print(f'uploaded file_id={fid}')

# 2) immediately create record referencing it
r2 = httpx.post(f'http://localhost:13002/api/v2/create-record-and-attach?user_id={USER}',
                json={'target_table':'health_records',
                      'record':{'title':'OCR-banner test','record_type':'other','importance':'medium'},
                      'attached_file_ids':[fid]},
                headers={'Authorization': 'Bearer '+tok, 'Idempotency-Key': f'k-{int(time.time())}'},
                timeout=15)
print(f'create: {r2.status_code} {r2.text[:200]}')

# 3) immediately fetch list - is ocr_status showing pending?
r3 = httpx.get('http://localhost:13002/api/health-records', headers={'Authorization': 'Bearer '+tok}, timeout=10)
recs = r3.json()
target = next((x for x in recs if x.get('title') == 'OCR-banner test'), None)
if target:
    print(f'target record id={target["id"]}')
    print(f'  files (top level) = {target.get("files")}')
    print(f'  metadata._attached_files_meta = {target.get("metadata",{}).get("_attached_files_meta")}')
    if target.get('metadata',{}).get('_attached_files_meta'):
        f = target['metadata']['_attached_files_meta'][0]
        print(f'  -> ocr_status={f.get("ocr_status")!r}, file_name={f.get("file_name")!r}')
