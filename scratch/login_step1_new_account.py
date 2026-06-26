import json
import sys
import hashlib
import random
import time
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

def generate_pgbank_browser_id():
    # 32-char hex
    visitor_id = hashlib.md5(f"pgbank_{USERNAME}_{random.random()}".encode()).hexdigest()
    # timestamp in ms
    timestamp = int(time.time() * 1000)
    # 6 random chars
    rand_chars = "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(6))
    return f"{visitor_id}-{timestamp}-{rand_chars}"

def main():
    print("=== NEW ACCOUNT LOGIN STEP 1 ===")
    print(f"Username: {USERNAME}")
    
    # Generate a stable browser ID for this run, or reuse if we saved one
    if PENDING_OTP_PATH.exists():
        try:
            with open(PENDING_OTP_PATH) as f:
                saved = json.load(f)
            browser_id = saved.get("browser_id")
            print(f"Reusing saved browser ID: {browser_id}")
        except Exception:
            browser_id = generate_pgbank_browser_id()
            print(f"Generated new browser ID: {browser_id}")
    else:
        browser_id = generate_pgbank_browser_id()
        print(f"Generated new browser ID: {browser_id}")

    # Initialize the client without auto-login
    client = PGBankClient(
        username=USERNAME,
        password=PASSWORD,
        browser_id=browser_id,
        auto_login=False,
    )

    try:
        print("\nSending Login Step 1 request...")
        resp = client.login_step1()
        
        # Check response
        code = resp.get("code")
        print(f"Result code: {code}")
        
        if code == "00":
            print("SUCCESS! Logged in without OTP.")
            print(f"Customer Name: {client.full_name}")
            print(f"Session ID: {client.session_id}")
        elif code in ("01", "114"):
            print(f"Raw Response: {json.dumps(resp, indent=2)}")
            ref_no = resp.get("refNo", resp.get("otpRefNo", resp.get("txnToken")))
            otp_token = resp.get("token", client.token)
            print("\n>>> OTP IS REQUIRED! <<<")
            print(f"Ref No (Mã tham chiếu): {ref_no}")
            print(f"OTP Token: {otp_token[:40]}...")
            
            # Save the pending state to file
            state = {
                "username": USERNAME,
                "password": PASSWORD,
                "browser_id": browser_id,
                "ref_no": ref_no,
                "otp_token": otp_token,
            }
            with open(PENDING_OTP_PATH, "w") as f:
                json.dump(state, f, indent=2)
            print(f"\nSaved pending OTP state to: {PENDING_OTP_PATH}")
            print("\n>>> Please read the OTP sent to your SIM and run the confirm script! <<<")
        else:
            print(f"Login failed: {resp.get('des')}")
            
    except Exception as e:
        print(f"Error during login: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    main()
