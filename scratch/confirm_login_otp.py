import json
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
from pgbank_unofficial.exceptions import AuthenticationError

USERNAME = "0566150141"
PASSWORD = "Bau@6789"
PENDING_OTP_PATH = Path(__file__).parent / "pending_otp_new_account.json"
SESSION_PATH = Path(__file__).parent / "test_session_new_account.json"

def main():
    print("=== NEW ACCOUNT LOGIN STEP 2 ===")
    
    if not PENDING_OTP_PATH.exists():
        print("Error: pending_otp_new_account.json not found!")
        return

    with open(PENDING_OTP_PATH) as f:
        saved = json.load(f)

    browser_id = saved.get("browser_id")
    # In the previous run, ref_no was null, but the raw response had txnToken = "765962"
    ref_no = saved.get("ref_no") or "765962"
    otp_token = saved.get("otp_token")

    print(f"Username: {USERNAME}")
    print(f"Browser ID: {browser_id}")
    print(f"Ref No: {ref_no}")
    print(f"OTP Token: {otp_token[:40]}...")
    
    # Read OTP from command line argument if provided, else use default
    otp = "336093"
    if len(sys.argv) > 1:
        otp = sys.argv[1]
    
    print(f"Submitting OTP: {otp}")

    client = PGBankClient(
        username=USERNAME,
        password=PASSWORD,
        browser_id=browser_id,
        session_path=SESSION_PATH,
        auto_login=False,
    )

    # Set the pending OTP state
    client._otp_required = True
    client._pending_otp_ref = ref_no
    client._pending_otp_token = otp_token

    try:
        resp = client.login_step2(otp=otp)
        print("\n=== LOGIN STEP 2 SUCCESS! ===")
        print(f"Response: {json.dumps(resp, indent=2)}")
        print(f"Session ID: {client.session_id}")
        print(f"Full Name: {client.full_name}")
        print(f"Saved session to {SESSION_PATH}")
    except AuthenticationError as e:
        print(f"\nAuthentication Error: {e} (Reason: {e.reason})")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    main()
