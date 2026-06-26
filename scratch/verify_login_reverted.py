import sys
from pathlib import Path

# Force UTF-8 encoding for stdout/stderr
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pgbank_unofficial import PGBankClient

USERNAME = "0567952139"
PASSWORD = "Bau@6789"
BROWSER_ID = "5e3adf3f155437c827962d2714747b4258536-1779697320812-qhi626"
SESSION_PATH = Path(__file__).parent / "test_session.json"

def main():
    print(f"Testing login with password: {PASSWORD}")
    if SESSION_PATH.exists():
        SESSION_PATH.unlink()
        print("Cleared session file to force fresh login.")
        
    client = PGBankClient(
        username=USERNAME,
        password=PASSWORD,
        browser_id=BROWSER_ID,
        session_path=SESSION_PATH,
        auto_login=False,
    )
    
    try:
        client.login()
        print("Login Success!")
        print(f"Session ID: {client.session_id[:10]}...")
        print(f"Customer Name: {client.full_name}")
        bal = client.get_balance()
        print(f"Primary Account: {bal.account_number}")
        print(f"Available Balance: {bal.available} {bal.currency}")
    except Exception as e:
        print(f"Login Failed: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    main()
