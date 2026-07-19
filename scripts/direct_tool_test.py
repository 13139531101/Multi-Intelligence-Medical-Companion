"""Direct tool call with real user_id."""
import os
os.environ['MEMORY_DB_PASSWORD'] = 'zTlQevKV5vzq31QzRqwfcauKX3uQZ64c'

# Call get_today_reminders with real user_id
import sys
sys.path.insert(0, '/app/backend/MedicationReminder/mcpserver')

# Setup DB env
os.environ.setdefault('MEMORY_DB_HOST', 'postgres')

from reminder_tool import get_today_reminders, get_medication_reminders
import json

uid = "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"

print("=== get_today_reminders ===")
r1 = get_today_reminders(uid)
print(json.dumps(r1, ensure_ascii=False, indent=2, default=str))

print("\n=== get_medication_reminders ===")
r2 = get_medication_reminders(uid)
print(json.dumps(r2, ensure_ascii=False, indent=2, default=str))
