import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pgbank_unofficial import PGBankClient

USERNAME = "0567952139"
PASSWORD = "Bau@6789"
BROWSER_ID = "5e3adf3f155437c827962d2714747b4258536-1779697320812-qhi626"
SESSION_PATH = Path(__file__).parent / "test_session.json"

def main():
    if SESSION_PATH.exists():
        SESSION_PATH.unlink()
    client = PGBankClient(
        username=USERNAME,
        password=PASSWORD,
        browser_id=BROWSER_ID,
        session_path=SESSION_PATH,
        auto_login=True,
    )
    
    print(f"Logged in: {client.is_logged_in}")
    if client.is_logged_in:
        print("\n--- Try querying contact list with various payloads ---")
        payloads = [
            {"beneType": "1,2,3"},
            {"userName": USERNAME, "beneType": "1,2,3"},
            {"serviceCode": "0102"},
            {},
        ]
        for p in payloads:
            print(f"\nQuerying payload: {p}")
            try:
                resp = client._post("utility-service", "8014", p)
                print(json.dumps(resp, indent=2, default=str))
            except Exception as e:
                print(f"Error querying {p}: {e}")
                
    client.close()

if __name__ == "__main__":
    main()
