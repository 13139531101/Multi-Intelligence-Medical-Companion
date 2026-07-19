"""Test mcp_discover + PhaCore 工具发现."""
import sys
sys.path.insert(0, 'backend/A2AServer/src')

from A2AServer.v2.mcp_discover import discover_mcp_tools_static, discover_phacore_tools

print("=== PhaCore tools (NEW, 阶段 48-19) ===")
phacore = discover_phacore_tools()
for t in phacore:
    print(f"  - {t['name']} (from {t.get('module', '?')}, file={t.get('file', '?').rsplit(chr(92), 1)[-1]})")

print()
print("=== HealthRecordsManager tools (现在应该 OCR 部分被搬走) ===")
hrm = discover_mcp_tools_static('health_records')
print(f"  total HRM tools: {len(hrm)}")
ocr_in_hrm = [t for t in hrm if t['name'] in ('extract_text_from_image', 'validate_medical_document')]
print(f"  OCR 重复: {len(ocr_in_hrm)} 个 (目标: 0)")
for t in ocr_in_hrm:
    print(f"  ! {t['name']} still in HRM")

print()
print("=== MedicationReminder tools (应该没有 OCR 了) ===")
med = discover_mcp_tools_static('medication_reminder')
print(f"  total MedReminder tools: {len(med)}")
ocr_in_med = [t for t in med if t['name'] in ('extract_text_from_image', 'validate_medical_document')]
print(f"  OCR 重复: {len(ocr_in_med)} 个 (目标: 0)")
for t in ocr_in_med:
    print(f"  ! {t['name']} still in MedReminder")

print()
print(f"=== 总结 (阶段 48-19 phase 1 状态) ===")
print(f"PhaCore tools: {len(phacore)}")
print(f"OCR 剩余重复 (HRM + MedReminder): {len(ocr_in_hrm) + len(ocr_in_med)}")
print(f"目标: 0 OCR 重复")
