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
        if not client.is_alive():
            print("Session expired, logging in fresh...")
            client.login()
    else:
        print("Please log in first")
        return
        
    confirm_keys = [
        "newPasswordVerify",
        "verifyNewPassword",
        "verifyPassword",
        "newPasswordValidation",
        "newPasswordValidate",
        "newPassConfirm",
        "retypeNewPass",
        "newPasswordRetype",
        "retype",
        "newPasswordCheck",
        "checkNewPassword",
        "confirmNewPassword", # double check
        "confirmPassword",    # double check
        "renewPassword",      # double check
        "reNewPassword",      # double check
        "newPasswordConfirm", # double check
        "passwordConfirm",    # double check
        "rePassword",         # double check
        "retypeNewPassword",  # double check
        "retypePassword",     # double check
        "confirmNewPass",     # double check
        "reNewPass",          # double check
        "confirm",            # double check
        "repass",             # double check
    ]
    
    print("\n=== Probing Confirmation Password Keys ===")
    for key in confirm_keys:
        p = {
            "oldPassword": PASSWORD,
            "newPassword": "Bank@999",
            key: "Bank@999"
        }
        print(f"\nProbing key: {key}")
        try:
            resp = client._post("auth-service", "2001", p)
            code = resp.get("code")
            msg = resp.get("des", "")
            print(f"  Result code: {code}, message: {repr(msg)}")
            if code != "01" or "không trùng khớp" not in msg:
                print(f"  🎉 FOUND POTENTIAL KEY: {key} !!! Response: {json.dumps(resp, indent=2, default=str)}")
        except Exception as e:
            print(f"  Error: {repr(e)}")
                
    client.close()

if __name__ == "__main__":
    main()
