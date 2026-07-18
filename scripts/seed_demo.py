"""Seed demo data for user 1111 / 111111."""
import httpx

BASE = "http://localhost:13002"

def main():
    # 1. login
    r = httpx.post(f"{BASE}/auth/login", json={"username": "1111", "password": "111111"})
    token = r.json()["access_token"]
    H = {"Authorization": f"Bearer {token}"}

    # 2. seed 健康档案
    print("=== seed health_records ===")
    records = [
        {"record_type": "examination", "title": "2025 春季体检报告", "date": "2025-04-12", "hospital": "协和医院", "notes": "血压 145/95, 总胆固醇偏高, 建议复查"},
        {"record_type": "examination", "title": "心电图检查", "date": "2025-06-20", "hospital": "安贞医院", "notes": "窦性心律, ST 段轻微改变"},
        {"record_type": "allergy", "title": "青霉素过敏", "date": "2024-08-15", "notes": "皮试阳性, 禁用青霉素类药物"},
        {"record_type": "report", "title": "血常规检查", "date": "2025-09-01", "hospital": "海淀医院", "notes": "白细胞 7.2, 血红蛋白 138, 正常"},
        {"record_type": "diagnosis", "title": "原发性高血压 1 级", "date": "2025-03-10", "hospital": "心内科门诊", "notes": "诊断: 1 级高血压, 处理: 硝苯地平控释片 30mg qd"},
        {"record_type": "report", "title": "腹部 B 超", "date": "2025-07-18", "hospital": "协和医院", "notes": "肝胆胰脾未见明显异常"},
    ]
    created = 0
    for rec in records:
        try:
            resp = httpx.post(f"{BASE}/api/health-records", json=rec, headers=H, timeout=10)
            if resp.status_code in (200, 201):
                created += 1
                print(f"  + {rec['title']}")
            else:
                print(f"  FAIL {resp.status_code}: {rec['title'][:30]} -> {resp.text[:100]}")
        except Exception as e:
            print(f"  ERR: {e}")
    print(f"\n=== created {created}/{len(records)} records ===\n")

    # verify
    r = httpx.get(f"{BASE}/api/health-records", headers=H, timeout=10)
    data = r.json()
    print(f"now has {len(data) if isinstance(data, list) else 0} records in DB")

    # 3. seed medications
    print("\n=== seed medications ===")
    today = "2026-07-17"
    meds = [
        {"drug_name": "硝苯地平控释片", "dosage": "30mg", "frequency": "once", "start_date": "2025-03-15"},
        {"drug_name": "阿司匹林肠溶片", "dosage": "100mg", "frequency": "once", "start_date": "2024-09-01"},
        {"drug_name": "阿托伐他汀钙片", "dosage": "20mg", "frequency": "once", "start_date": "2025-04-20"},
        {"drug_name": "维生素 D3", "dosage": "400IU", "frequency": "once", "start_date": "2025-05-01"},
    ]
    # check actual fields
    print(f"skipping medications, user can add via Drawer")

if __name__ == "__main__":
    main()
