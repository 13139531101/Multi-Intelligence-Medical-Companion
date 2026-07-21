import httpx, json
r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"}, timeout=10)
tok = r.json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
fid = "362abdbb-bc03-4307-9318-0dd5b928a619"
r2 = httpx.get(f"http://localhost:13002/v2/upload/files/{fid}/parsed",
               params={"user_id": "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"}, headers=H, timeout=15)
d = r2.json()
print(f"fields count: {len(d['parsed']['fields'])}")
print(f"sections count: {len(d['parsed']['sections'])}")
print(f"summary: {d['parsed']['summary']}")
for s in d["parsed"]["sections"]:
    print(f"  - {s['title']}: {len(s['paras'])} para, {len(s['chips'])} chips")
    if s["chips"]:
        print(f"    chips={s['chips'][:6]}")
