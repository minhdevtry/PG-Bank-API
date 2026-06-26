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
from pgbank_unofficial.exceptions import PGBankError

USERNAME = "0567952139"
PASSWORD = "Bau@6789"
BROWSER_ID = "5e3adf3f155437c827962d2714747b4258536-1779697320812-qhi626"
SESSION_PATH = Path(__file__).parent / "test_session.json"

def main():
    print("=== LIVE CONTACT CRUD INTEGRATION TEST ===")
    
    # 1. Initialize PGBank client (will auto-login if session expired)
    client = PGBankClient(
        username=USERNAME,
        password=PASSWORD,
        browser_id=BROWSER_ID,
        session_path=SESSION_PATH,
        auto_login=True,
    )
    
    print("Checking if session is alive (auto-renews if expired)...")
    if not client.is_alive():
        print("Session not alive. Logging in fresh...")
        client.login()
        
    print(f"Logged in successfully. Customer: {client.full_name}")
    
    # 2. Retrieve initial contacts list
    print("\nStep 1: Fetching current contacts...")
    contacts = client.get_contacts()
    print(f"Total contacts found: {len(contacts)}")
    for c in contacts:
        print(f"  - ID: {c.get('id')}, Nickname: {c.get('name')}, Pan: {c.get('pan')}, BeneName: {c.get('beneName')}, Fav: {c.get('favourite')}")

    # Techcombank 4222226789 (NGUYEN MINH SON)
    test_nickname = "Test Son Techcom"
    test_account = "4222226789"
    test_bank_code = "970407"
    test_bank_name = "Techcombank"
    test_bene_name = "NGUYEN MINH SON"

    # Pre-cleanup: if the target account already exists, delete it first to avoid duplicate errors
    existing_id = None
    for c in contacts:
        if c.get("pan") == test_account:
            existing_id = c.get("id")
            break
            
    if existing_id:
        print(f"\n[Cleanup] Contact for account {test_account} already exists (ID: {existing_id}). Deleting it first...")
        client.delete_contact(existing_id)
        print("[Cleanup] Successfully deleted existing contact to avoid duplicate error.")
        # Re-fetch contacts to be clean
        contacts = client.get_contacts()

    # 3. Create a new contact
    print(f"\nStep 2: Creating new contact '{test_nickname}' for account {test_account}...")
    try:
        create_resp = client.create_contact(
            name=test_nickname,
            receiver_account=test_account,
            bank_code=test_bank_code,
            bank_name=test_bank_name,
            bene_name=test_bene_name,
            bene_type="2", # NAPAS interbank
            favourite=False,
        )
        print("Contact created successfully!")
        print(json.dumps(create_resp, indent=2, default=str))
    except Exception as e:
        print(f"Error creating contact: {e}")
        client.close()
        return

    # 4. Fetch contacts list again to find the created contact and get its ID
    print("\nStep 3: Finding the newly created contact...")
    contacts = client.get_contacts()
    target_contact = None
    for c in contacts:
        if c.get("pan") == test_account and c.get("name") == test_nickname:
            target_contact = c
            break
            
    if not target_contact:
        print("Error: Newly created contact not found in list!")
        client.close()
        return
        
    bene_id = target_contact.get("id")
    print(f"Found contact! ID: {bene_id}, Nickname: {target_contact.get('name')}, Fav: {target_contact.get('favourite')}")

    # 5. Update contact (Mark as Favourite and change Nickname)
    updated_nickname = "Test Son Fav"
    print(f"\nStep 4: Updating contact {bene_id} (Nickname -> '{updated_nickname}', Favourite -> True)...")
    try:
        update_resp = client.update_contact(
            bene_id=bene_id,
            name=updated_nickname,
            favourite=True,
        )
        print("Contact updated successfully!")
        print(json.dumps(update_resp, indent=2, default=str))
    except Exception as e:
        print(f"Error updating contact: {e}")

    # Verify update in contacts list
    print("\nStep 5: Verifying update in contacts list...")
    contacts = client.get_contacts()
    updated_contact = None
    for c in contacts:
        if c.get("id") == bene_id:
            updated_contact = c
            break
            
    if updated_contact:
        print(f"Verification: Nickname is '{updated_contact.get('name')}', Favourite is {updated_contact.get('favourite')}")
        assert updated_contact.get("name") == updated_nickname
        assert updated_contact.get("favourite") is True
        print("Update verified successfully!")
    else:
        print("Error: Updated contact not found in list!")

    # 6. Delete the contact
    print(f"\nStep 6: Deleting contact {bene_id}...")
    try:
        delete_resp = client.delete_contact(bene_id)
        print("Contact deleted successfully!")
        print(json.dumps(delete_resp, indent=2, default=str))
    except Exception as e:
        print(f"Error deleting contact: {e}")

    # 7. Final verification
    print("\nStep 7: Verifying contact deletion...")
    contacts = client.get_contacts()
    deleted_still_exists = any(c.get("id") == bene_id for c in contacts)
    if not deleted_still_exists:
        print("SUCCESS: Contact is no longer in the list!")
    else:
        print("FAILURE: Contact still exists in the list after deletion!")

    client.close()

if __name__ == "__main__":
    main()
