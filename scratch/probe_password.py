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
        # Check if the session is alive, if not it will automatically log in fresh
        if not client.is_alive():
            print("Session expired, logging in fresh...")
            client.login()
    else:
        print("Please log in first")
        return
        
    services = ["auth-service"]
    payloads = [
        {"oldPassword": PASSWORD, "newPassword": "Bank@999", "rePassword": "Bank@999"},
        {"oldPassword": PASSWORD, "newPassword": "Bank@999", "newPasswordConfirm": "Bank@999"},
        {"oldPassword": PASSWORD, "newPassword": "Bank@999", "confirmNewPass": "Bank@999"},
        {"oldPassword": PASSWORD, "newPassword": "Bank@999", "retypeNewPassword": "Bank@999"},
        {"oldPassword": PASSWORD, "newPassword": "Bank@999", "retypePassword": "Bank@999"},
        {"oldPassword": PASSWORD, "newPassword": "Bank@999", "newPasswordRe": "Bank@999"},
        {"oldPassword": PASSWORD, "newPassword": "Bank@999", "repass": "Bank@999"},
        {"oldPassword": PASSWORD, "newPassword": "Bank@999", "confirm": "Bank@999"},
        {"oldPassword": PASSWORD, "newPassword": "Bank@999", "reNewPass": "Bank@999"},
        {"oldPassword": PASSWORD, "newPassword": "Bank@999", "passwordConfirm": "Bank@999"},
    ]
    
    print("\n=== Probing Change Password Endpoint ===")
    for svc in services:
        for p in payloads:
            print(f"\n--- Svc: {svc}, Payload: {p} ---")
            try:
                # We bypass the client wrapper and call _post directly
                resp = client._post(svc, "2001", p)
                print(f"Response: {json.dumps(resp, indent=2, default=str)}")
            except Exception as e:
                print(f"Error: {repr(e)}")
                
    client.close()

if __name__ == "__main__":
    main()
