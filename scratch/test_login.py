"""Test login flow with real PGBank credentials.

Account info:
- Username: 0567952139
- Password: Bau@6789
- Browser ID: 5e3adf3f155437c827962d2714747b4258536-1779697320812-qhi626
- Phone: 0567952139 (used for OTP delivery)

Test plan:
1. Try to restore old session — might still be valid
2. If expired, do login_step1 to see OTP challenge
3. Print all info we can get
"""
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pgbank_unofficial import PGBankClient
from pgbank_unofficial.exceptions import AuthenticationError, PGBankError

USERNAME = "0567952139"
PASSWORD = "Bank@999"
BROWSER_ID = "5e3adf3f155437c827962d2714747b4258536-1779697320812-qhi626"
SESSION_PATH = Path(__file__).parent / "test_session.json"


def banner(msg):
    print("\n" + "=" * 60)
    print(msg)
    print("=" * 60)


def main():
    banner("1. Initialize PGBankClient with saved session path")
    print(f"Username: {USERNAME}")
    print(f"Browser ID: {BROWSER_ID}")
    print(f"Session path: {SESSION_PATH}")
    print()

    # First try: load existing session
    banner("2. Try to load and use existing session")
    try:
        # Use the session file we found in the DB
        if SESSION_PATH.exists():
            print(f"Session file exists: {SESSION_PATH}")
            print(f"  Size: {SESSION_PATH.stat().st_size} bytes")
            with open(SESSION_PATH) as f:
                sess = json.load(f)
            print(f"  Session fields: {list(sess.keys())}")
            print(f"  Token starts: {sess.get('token', '')[:40]}...")
            print(f"  CIF: {sess.get('cif')}")
            print(f"  Account: {sess.get('accountNo')}")
            print(f"  Full name: {sess.get('fullName')}")
            print()

        # Create client with auto_login=True and session_path
        client = PGBankClient(
            username=USERNAME,
            password=PASSWORD,
            browser_id=BROWSER_ID,
            session_path=SESSION_PATH,
            auto_login=True,  # Will try to restore session first
            timeout=30,
        )

        print(f"Client initialized. is_logged_in: {client.is_logged_in}")
        print(f"  Session ID: {client.session_id[:40] if client.session_id else '(none)'}...")
        print(f"  CIF: {client.cif}")
        print(f"  Full name: {client.full_name}")

        if client.is_logged_in:
            print("\n  [OK] Session restored successfully!")

            # Try get_customer_info to verify session is still alive
            banner("3. Verify session by calling get_customer_info")
            try:
                # Let's call the raw post to see what it returns
                print("Raw GET_CUSTOMER_INFO (8041) response:")
                profile_raw = client._post("utility-service", "8041", {})
                print(json.dumps(profile_raw, indent=2))
                
                print("\nRaw GET_ACCOUNT_PAYMENTS (3004) response:")
                accounts_raw = client._post("bank-service", "3004", {})
                print(json.dumps(accounts_raw, indent=2))
                
                info = client.get_customer_info()
                print(f"  Customer ID: {info.customer_id}")
                print(f"  Customer name: {info.customer_name}")
                print(f"  Accounts: {len(info.accounts)}")
                for acc in info.accounts:
                    print(f"    - {acc.account_number} ({acc.account_name}): {acc.balance} {acc.currency}")
                print("\n  [OK] Live API call SUCCESS!")
            except Exception as e:
                print(f"  [FAIL] Live API call FAILED: {type(e).__name__}: {e}")

            # Try get_balance
            banner("4. Try get_balance on primary account")
            try:
                print("Raw AVAILABLE_BALANCE (3008) response:")
                balance_raw = client._post("bank-service", "3008", {"accountNumber": "2883621213010"})
                print(json.dumps(balance_raw, indent=2))
                
                balance = client.get_balance()
                print(f"  Account: {balance.account_number}")
                print(f"  Available: {balance.available} {balance.currency}")
                print(f"  Total: {balance.total} {balance.currency}")
                print(f"  As of: {balance.as_of}")
                print("\n  [OK] get_balance SUCCESS!")
            except Exception as e:
                print(f"  [FAIL] get_balance FAILED: {type(e).__name__}: {e}")

        else:
            print("\n  Session NOT loaded. Trying fresh login_step1...")

            banner("3. Fresh login_step1")
            try:
                resp = client.login_step1()
                print(f"  Response: {json.dumps(resp, indent=2, default=str)}")
                if resp.get("sessionId"):
                    print("\n  [OK] Login step 1 returned sessionId — NO OTP required")
                    print(f"  sessionId: {resp['sessionId'][:40]}...")
                elif resp.get("refNo") and resp.get("otpToken"):
                    print("\n  [WARNING] OTP REQUIRED (refNo + otpToken returned)")
                    print(f"  refNo: {resp['refNo']}")
                    print(f"  otpToken: {resp['otpToken']}")
                    print(f"  message: {resp.get('message', '(none)')}")
                    print("\n  → You need to provide OTP from SMS (0567952139)")
                    print("  → Run: python scratch/submit_otp.py YOUR_OTP")
                else:
                    print(f"\n  ? Unexpected response: {list(resp.keys())}")
            except Exception as e:
                print(f"  [FAIL] login_step1 FAILED: {type(e).__name__}: {e}")

        client.close()
    except Exception as e:
        print(f"\n[ERROR] Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
