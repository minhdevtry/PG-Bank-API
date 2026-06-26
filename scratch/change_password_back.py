import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pgbank_unofficial import PGBankClient
from pgbank_unofficial.exceptions import PGBankError

USERNAME = "0567952139"
CURRENT_PASSWORD = "Bank@999"
TARGET_PASSWORD = "Bau@6789"
BROWSER_ID = "5e3adf3f155437c827962d2714747b4258536-1779697320812-qhi626"
SESSION_PATH = Path(__file__).parent / "test_session.json"

def main():
    print(f"Initializing PGBankClient with CURRENT_PASSWORD: {CURRENT_PASSWORD}...")
    
    # 1. Initialize client using the CURRENT password
    client = PGBankClient(
        username=USERNAME,
        password=CURRENT_PASSWORD,
        browser_id=BROWSER_ID,
        session_path=SESSION_PATH,
        auto_login=True,
    )
    
    print(f"Logged in status: {client.is_logged_in}")
    if not client.is_logged_in:
        print("Not logged in. Performing login...")
        client.login()
        print(f"Login success! Session ID: {client.session_id[:10]}...")

    # Verify session is alive
    if not client.is_alive():
        print("Session not alive. Retrying login...")
        client.login()
        
    print(f"Customer Name: {client.full_name}")

    # 2. Change password back to TARGET_PASSWORD
    print(f"\nChanging password back from {CURRENT_PASSWORD} -> {TARGET_PASSWORD}...")
    try:
        resp = client.change_password(CURRENT_PASSWORD, TARGET_PASSWORD)
        print(f"Password changed successfully! Response: {json.dumps(resp, indent=2)}")
    except Exception as e:
        print(f"Error changing password: {e}")
        client.close()
        return

    # Close current client session
    client.close()
    
    # 3. Clean up the session path to force a fresh login with the reverted password
    if SESSION_PATH.exists():
        SESSION_PATH.unlink()
        print("\nSession file cleared.")

    # 4. Instantiate a new client using the reverted TARGET_PASSWORD to verify it works!
    print(f"\nInstantiating a new client with TARGET_PASSWORD: {TARGET_PASSWORD} to verify...")
    new_client = PGBankClient(
        username=USERNAME,
        password=TARGET_PASSWORD,
        browser_id=BROWSER_ID,
        session_path=SESSION_PATH,
        auto_login=False,
    )
    
    try:
        new_client.login()
        print(f"🎉 SUCCESS! Logged in successfully with reverted password: {TARGET_PASSWORD}")
        print(f"Session ID: {new_client.session_id[:10]}...")
        print(f"Customer Name: {new_client.full_name}")
        
        # Verify get_balance
        bal = new_client.get_balance()
        print(f"Balance of account {bal.account_number}: {bal.available} {bal.currency}")
    except Exception as e:
        print(f"❌ FAILED to log in with reverted password: {e}")
    finally:
        new_client.close()

if __name__ == "__main__":
    main()
