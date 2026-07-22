import psycopg2
dsn = 'host=localhost port=5432 dbname=personal_health user=postgres password=pha_pass'
try:
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute('SELECT id, title, type, tags FROM health_records ORDER BY created_at DESC LIMIT 6')
    for r in cur.fetchall():
        print(r[0], '|', r[1], '|', r[2], '|', type(r[3]).__name__, '=', repr(r[3])[:200])
except Exception as e:
    print('FAIL:', e)
