"""Find browser_id for the test account 0567952139."""
import sqlite3
import json
from pathlib import Path

# Try the most recent database
db_paths = [
    r"C:\Users\vanto\Documents\code\VCB-API\pg\pgbank\apps\admin\data\admin_dashboard.sqlite3",
    r"C:\Users\vanto\Documents\code\VCB-API\pg\pgbank\apps\function_server\data\function_server.sqlite3",
    r"C:\Users\vanto\Documents\code\VCB-API\pg\pgbank\pgbank\data\admin_dashboard.sqlite3",
]

for db_path in db_paths:
    p = Path(db_path)
    if not p.exists():
        continue
    print(f"\n=== {db_path} ===")
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
        print(f"Tables: {tables}")

        # Try common table names
        for table in tables:
            if "bank" in table.lower() or "account" in table.lower() or "user" in table.lower():
                print(f"\n--- {table} ---")
                try:
                    cur.execute(f"PRAGMA table_info({table})")
                    cols = [row[1] for row in cur.fetchall()]
                    print(f"Cols: {cols}")
                    # Try to find row with username 0567952139
                    if "username" in cols:
                        cur.execute(f"SELECT * FROM {table} WHERE username LIKE '0567952139%'")
                        rows = cur.fetchall()
                        for row in rows:
                            d = dict(zip(cols, row))
                            print(json.dumps(d, indent=2, default=str))
                    elif "account_number" in cols:
                        cur.execute(f"SELECT * FROM {table} WHERE account_number LIKE '0567952139%'")
                        rows = cur.fetchall()
                        for row in rows:
                            d = dict(zip(cols, row))
                            print(json.dumps(d, indent=2, default=str))
                except Exception as e:
                    print(f"Error: {e}")
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

# Also try accounts.json
accounts_json = r"C:\Users\vanto\Documents\code\VCB-API\pg\pgbank\accounts.json"
p = Path(accounts_json)
if p.exists():
    print(f"\n=== accounts.json ===")
    try:
        data = json.loads(p.read_text())
        if isinstance(data, list):
            for entry in data:
                if entry.get("username") == "0567952139":
                    print(json.dumps(entry, indent=2, default=str))
        elif isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict) and v.get("username") == "0567952139":
                    print(f"Key: {k}")
                    print(json.dumps(v, indent=2, default=str))
    except Exception as e:
        print(f"Error: {e}")
