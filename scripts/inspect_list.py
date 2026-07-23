import httpx, json
tok = httpx.post('http://localhost:13002/auth/login', json={'username':'1111','password':'111111'}, timeout=10).json()['access_token']
r = httpx.get('http://localhost:13002/api/health-records', headers={'Authorization': 'Bearer '+tok}, timeout=10)
recs = r.json()
print(f'total records: {len(recs)}')
for i, rec in enumerate(recs[:6]):
    files = rec.get('files') or rec.get('file_attachments') or []
    meta = rec.get('metadata') or {}
    print(f'--- record {i}: title={rec.get("title")!r}, files_len={len(files)}')
    print(f'   files_keys (first item): {[k for k in (files[0].keys() if files and isinstance(files[0], dict) else [])] if files else "no files"}')
    print(f'   metadata.files = {meta.get("files")!r}')
    print(f'   metadata._attached_files_meta = {str(meta.get("_attached_files_meta"))[:200]}')
    print()
