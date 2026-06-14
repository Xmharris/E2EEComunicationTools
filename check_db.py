import sqlite3
conn = sqlite3.connect(r'C:\Users\xavie\Documents\antigravity\quick-franklin\na_meetings.db')
cursor = conn.cursor()
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
for t in tables:
    print(t[0])

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
table_names = [r[0] for r in cursor.fetchall()]
for name in table_names:
    cursor.execute(f"SELECT COUNT(*) FROM {name}")
    print(f"Table {name} has {cursor.fetchone()[0]} rows")
