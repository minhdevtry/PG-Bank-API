"""Check saved session for the test account."""
import sqlite3
import json
from pathlib import Path

db_path = r"C:\Users\vanto\Documents\code\VCB-API\pg\pgbank\apps\admin\data\admin_dashboard.sqlite3"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print("=== bank_account_sessions ===")
cur.execute("SELECT account_id, session_json, updated_at FROM bank_account_sessions")
for row in cur.fetchall():
    if "0567952139" in row[0] or "0567952139" in row[1]:
        print(f"Account: {row[0]}")
        print(f"Updated: {row[2]}")
        try:
            sess = json.loads(row[1])
            # Show key fields, mask token if needed
            masked = {}
            for k, v in sess.items():
                if isinstance(v, str) and len(v) > 30:
                    masked[k] = v[:30] + "...(truncated)"
                else:
                    masked[k] = v
            print(f"Session: {json.dumps(masked, indent=2, default=str)}")
            # Save the full session to a file for re-use
            out_path = Path(r"C:\Users\vanto\Documents\code\VCB-API\pgbank-unofficial\scratch\test_session.json")
            out_path.write_text(json.dumps(sess, indent=2))
            print(f"Full session saved to: {out_path}")
        except Exception as e:
            print(f"Raw: {row[1][:200]}")
            print(f"Error: {e}")
        print()

print("\n=== bank_account_pending_logins ===")
cur.execute("SELECT account_id, status, otp_ref_no, otp_token, raw_json, error, created_at FROM bank_account_pending_logins ORDER BY created_at DESC LIMIT 5")
for row in cur.fetchall():
    print(f"Account: {row[0]}")
    print(f"Status: {row[1]}")
    print(f"OTP Ref: {row[2]}")
    print(f"OTP Token: {row[3]}")
    print(f"Error: {row[5]}")
    print(f"Created: {row[6]}")
    if row[4]:
        try:
            raw = json.loads(row[4])
            print(f"Raw (truncated): {json.dumps(raw, indent=2, default=str)[:500]}")
        except:
            print(f"Raw: {row[4][:200]}")
    print()

conn.close()
