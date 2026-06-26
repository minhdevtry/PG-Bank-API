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
    client = PGBankClient(
        username=USERNAME,
        password=PASSWORD,
        browser_id=BROWSER_ID,
        session_path=SESSION_PATH,
        auto_login=True,
    )
    
    print(f"Logged in: {client.is_logged_in}")
    if client.is_logged_in:
        print("\n--- Try looking up receiver name for Techcombank 4222226789 ---")
        try:
            # 5009 is MID for GET_RECEIVER_NAME_NAPAS
            payload = {
                "identifier": "4222226789",
                "bankCode": "970407", # Techcombank 247
                "beneficiaryName": "",
                "sourceAccount": "2883621213010",
            }
            resp = client._post("bank-service", "5009", payload)
            print(json.dumps(resp, indent=2, default=str))
        except Exception as e:
            print(f"Error: {e}")
                
    client.close()

if __name__ == "__main__":
    main()
