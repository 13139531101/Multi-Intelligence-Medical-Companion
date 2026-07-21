import httpx, json
r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"}, timeout=10)
tok = r.json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
fid = "362abdbb-bc03-4307-9318-0dd5b928a619"
r2 = httpx.get(f"http://localhost:13002/v2/upload/files/{fid}/parsed",
               params={"user_id": "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"}, headers=H, timeout=15)
d = r2.json()
print("==fields==")
for f in d["parsed"]["fields"]:
    print(f"  {f['key']:8} filled={f['filled']:5} val={f['value'][:60]!r}")
print(f"\n==sections ({len(d['parsed']['sections'])})==")
for sec in d["parsed"]["sections"]:
    print(f"  {sec['title']}: {len(sec['paras'])} paras")
