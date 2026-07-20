import httpx
import io
import time
from PIL import Image, ImageDraw, ImageFont

# 1. Login
r = httpx.post("http://localhost:13002/auth/login", json={"username": "1111", "password": "111111"}, timeout=10)
tok = r.json()["access_token"]
hdr = {"Authorization": f"Bearer {tok}"}

# 2. Create a test image with text (中文)
img = Image.new("RGB", (640, 200), "white")
d = ImageDraw.Draw(img)
d.text((20, 40), "血常规检查报告", fill="black")
d.text((20, 80), "血红蛋白 130 g/L (正常)", fill="black")
d.text((20, 120), "白细胞 6.5 10^9/L", fill="black")
d.text((20, 160), "血小板 250 10^9/L", fill="black")
buf = io.BytesIO()
img.save(buf, format="JPEG", quality=85)
buf.seek(0)
img_bytes = buf.getvalue()
print(f"created test image: {len(img_bytes)} bytes")

# 3. Upload
r2 = httpx.post(
    "http://localhost:13002/v2/upload/file",
    files={"file": ("test_lab_report.jpg", buf, "image/jpeg")},
    data={"user_id": "user_4e3ef0b3f49d8d4433e0b4420a3bae2a", "domain": "pha", "purpose": "health_record"},
    headers=hdr,
    timeout=20,
)
print(f"upload: HTTP {r2.status_code}, body={r2.text[:200]}")
fid = r2.json().get("file_id", "")

# 4. Poll OCR status (wait up to 90s)
for i in range(18):
    time.sleep(5)
    r3 = httpx.get("http://localhost:13002/v2/upload/files",
                   params={"user_id": "user_4e3ef0b3f49d8d4433e0b4420a3bae2a", "purpose": "health_record", "limit": 5},
                   headers=hdr, timeout=10)
    for row in r3.json():
        if row["id"] == fid:
            print(f"[{i*5:3d}s] ocr_status={row['ocr_status']}, ocr_text_len={len(row.get('ocr_text') or '')}")
            if row["ocr_status"] in ("done", "failed"):
                print(f"\n=== OCR text ===\n{row.get('ocr_text') or '(empty)'}\n=== END ===")
                print(f"\n=== ocr_error ===\n{row.get('ocr_error') or '(none)'}")
                exit(0)

print("TIMED OUT waiting for OCR")
