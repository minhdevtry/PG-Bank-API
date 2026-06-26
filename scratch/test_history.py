import json
import sys
from datetime import datetime, timedelta
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
        print("\n--- Try fetching transaction history ---")
        try:
            # PGBank date format: YYYYMMDD
            to_date = datetime.now().strftime("%Y%m%d")
            from_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
            print(f"Date range: {from_date} -> {to_date}")
            
            # 3010 is MID for GET_TRANSACTION_HISTORY
            payload = {
                "accountNumber": "2883621213010",
                "fromDate": from_date,
                "toDate": to_date,
            }
            resp = client._post("bank-service", "3010", payload)
            print(json.dumps(resp, indent=2, default=str))
        except Exception as e:
            print(f"Error fetching history: {e}")
                
    client.close()

if __name__ == "__main__":
    main()
