import httpx, json
tok = httpx.post('http://localhost:13002/auth/login', json={'username':'1111','password':'111111'}, timeout=10).json()['access_token']
USER_ID = 'user_4e3ef0b3f49d8d4433e0b4420a3bae2a'
r = httpx.post(f'http://localhost:13002/api/v2/create-record-and-attach?user_id={USER_ID}',
               json={'target_table':'health_records','record':{'title':'测试单步','record_type':'lab_result','importance':'medium'},'attached_file_ids':[]},
               headers={'Authorization': 'Bearer '+tok,'Idempotency-Key':'test-1'},
               timeout=15)
print(f'status={r.status_code}')
print(f'body: {r.text[:400]}')
