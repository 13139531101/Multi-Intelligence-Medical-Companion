import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
from dotenv import dotenv_values
env = dotenv_values('.env')
for k, v in env.items():
    if v is not None and (k not in os.environ or not os.environ.get(k)):
        os.environ[k] = v
# 本地测试用 host port
os.environ['DB_HOST'] = '127.0.0.1'
os.environ['DB_PORT'] = '5432'
import psycopg
conn = psycopg.connect(
    host=os.environ['DB_HOST'],
    port=int(os.environ['DB_PORT']),
    user=os.environ['DB_USER'],
    password=os.environ['DB_PASSWORD'],
    dbname=os.environ.get('DB_NAME', 'personal_health_assistant'),
)
print('connected OK to', os.environ['DB_HOST'])
cur = conn.cursor()
cur.execute("SELECT 1")
print(cur.fetchone())
