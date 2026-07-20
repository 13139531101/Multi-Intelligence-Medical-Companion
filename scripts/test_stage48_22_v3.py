"""阶段48-22 v3+ 静态 / 集成检查 (无需运行 DB).

Tasks:
  A. 确认 HealthRecordForm 有 mode/create-edit 切换
  B. 确认 OCR inject 按钮存在
  C. 确认 NewHealthRecords 只有一个 '新增档案' 按钮
  D. 确认 backend PUT /api/v2/update-record-and-attach 路由存在

Usage: python scripts/test_stage48_22_v3.py
"""
from __future__ import annotations
import re
from pathlib import Path

REPO = Path(".").resolve()


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def check(label: str, ok: bool, note: str = ""):
    sym = "ok" if ok else "FAIL"
    print(f"  [{sym}] {label}" + (f"  ({note})" if note else ""))
    return ok


print("=" * 60)
print("阶段48-22 v3+ static check")
print("=" * 60)

# A. HealthRecordForm edit mode
form = read("frontend/multiagent_front/src/components/HealthRecordForm.jsx")
ok_a1 = "mode = \"create\"" in form
ok_a2 = "mode === \"edit\"" in form
ok_a3 = "/api/v2/update-record-and-attach" in form
ok_a4 = "initialToForm" in form
ok_a5 = "recordId" in form and "initialRecord" in form
print("\nA. HealthRecordForm edit mode")
check("mode prop default 'create'", ok_a1)
check("submit: dispatch PUT vs POST by mode", ok_a2)
check("endpoint: update-record-and-attach", ok_a3)
check("initialToForm helper", ok_a4)
check("recordId + initialRecord props", ok_a5)

# B. OCR inject
print("\nB. OCR auto-fill")
ok_b1 = "applyOcrToForm" in form
ok_b2 = "ContentCopyIcon" in form
ok_b3 = "OCR" in form and "summary" in form
check("applyOcrToForm helper", ok_b1)
check("ContentCopyIcon import", ok_b2)
check("OCR 注入到 form (summary+content)", ok_b3)

# C. NewHealthRecords 一个按钮
nhr = read("frontend/multiagent_front/src/pages/NewHealthRecords.jsx")
print("\nC. NewHealthRecords single entry")
imports_hrf = "HealthRecordForm" in nhr
no_top_upload = "setUploadOpen" not in nhr and "CloudUpload" not in nhr
ok_c1 = imports_hrf
ok_c2 = no_top_upload
check("HealthRecordForm imported", ok_c1)
check("no setUploadOpen / CloudUpload dead refs", ok_c2)

# D. Backend PUT
backend = read("backend/A2AServer/src/A2AServer/v2/record_create_api.py")
print("\nD. Backend PUT update endpoint")
ok_d1 = "@router.put(\"/update-record-and-attach\"" in backend
ok_d2 = "UpdateAndAttachRequest" in backend
ok_d3 = "_verify_record_ownership" in backend
check("PUT /update-record-and-attach route", ok_d1)
check("UpdateAndAttachRequest model", ok_d2)
check("ownership check before update", ok_d3)

# E. NewChat single entry (旧 AGENT_LIST 删了)
nc = read("frontend/multiagent_front/src/pages/NewChat.jsx")
print("\nE. NewChat 移除旧 AGENT_LIST 冗余")
ok_e1 = "AGENT_LIST.map" not in nc
check("AGENT_LIST map block removed", ok_e1)

# Summary
print("\n" + "=" * 60)
all_ok = all([ok_a1, ok_a2, ok_a3, ok_a4, ok_a5, ok_b1, ok_b2, ok_b3, ok_c1, ok_c2, ok_d1, ok_d2, ok_d3, ok_e1])
print(f"Summary: {'PASS' if all_ok else 'FAIL'} ({sum([ok_a1, ok_a2, ok_a3, ok_a4, ok_a5, ok_b1, ok_b2, ok_b3, ok_c1, ok_c2, ok_d1, ok_d2, ok_d3, ok_e1])}/14)")
print("=" * 60)

raise SystemExit(0 if all_ok else 1)
