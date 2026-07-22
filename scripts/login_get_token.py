import httpx, json, os
r = httpx.post("http://localhost:13002/auth/login",
               json={"username": "1111", "password": "111111"}, timeout=10)
data = r.json()
tok = data["access_token"]
out = {"token": tok, "user": data["user"]}
with open(r"I:\A2A\3\A2AServer\scripts\login_state.json", "w") as f:
    json.dump(out, f)
print("token len:", len(tok))
print("user:", data["user"]["username"])
