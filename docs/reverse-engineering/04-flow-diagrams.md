# Chapter 4: Flow Diagrams

This chapter contains Mermaid sequence diagrams illustrating the end-to-end communication flows between the unofficial API client, the browser, and the PGBank API Gateway.

---

## 1. Handshake & Bootstrapping

This initial phase fetches system properties and sets up the default credentials necessary to communicate with the API.

```mermaid
sequenceDiagram
    autonumber
    participant Client as Unofficial Client
    participant Static as ib.pgbank.com.vn
    
    rect rgb(240, 245, 255)
        note over Client, Static: Initialization (Once per Application Start)
        Client->>Static: GET /assets/mount/mount.json
        Static-->>Client: Returns JSON containing baseUrl, defaultToken, serverPubKey, HMAC config
        note over Client: Store defaultToken & serverPubKey
    end
```

---

## 2. Authentication Flow (New Device / Requires OTP)

If the client is authenticating from a new `browserId` or if session state is missing, the server challenges the client with a 2-step OTP flow.

```mermaid
sequenceDiagram
    autonumber
    participant Client as Unofficial Client
    participant Gateway as api-ib.pgbank.com.vn
    
    rect rgb(255, 240, 240)
        note over Client, Gateway: Step 1: Credentials Check
        note over Client: Generate ephemeral RSA keypair<br/>Calc HMAC Checksum on login fields
        Client->>Gateway: POST /auth-service/1004 (Login Payload)<br/>[Headers: Auth=Default Bearer, x-request-id]<br/>[Encrypted Envelope: userName, password, checkSum, clientPubKey]
        Gateway-->>Client: Returns Encrypted Response (code="01" / "114", message="OTP Required")<br/>[Payload: refNo, otpToken]
        note over Client: Store refNo & otpToken<br/>Prompt User/SMS-Forwarder for OTP
    end
    
    rect rgb(240, 255, 240)
        note over Client, Gateway: Step 2: OTP Verification
        note over Client: Clean OTP input (digits only)
        Client->>Gateway: POST /auth-service/1002 (Confirm OTP)<br/>[Encrypted Envelope: userName, otp, refNo, otpToken]
        Gateway-->>Client: Returns Encrypted Response (code="00", message="Success")<br/>[Payload: sessionId, token (session token), cif, fullName, mobileNo, etc.]
        note over Client: Apply Session: update client.token to the new session token<br/>Save session dictionary to local file
    end
```

---

## 3. Session Restoration (Bypassing OTP)

If a session is restored using a valid, non-expired session token and a trusted `browserId`, the client can skip Step 1 & 2.

```mermaid
sequenceDiagram
    autonumber
    participant Client as Unofficial Client
    participant File as Session JSON File
    participant Gateway as api-ib.pgbank.com.vn
    
    rect rgb(240, 245, 255)
        note over Client, File: Session Initialization
        Client->>File: Read saved token, CIF, keys
        note over Client: Restore keys, set is_logged_in = True
    end
    
    rect rgb(255, 255, 240)
        note over Client, Gateway: API Request (e.g., Get Balance)
        Client->>Gateway: POST /bank-service/3008 (Available Balance)<br/>[Headers: Auth=Session Token]<br/>[Encrypted Envelope: accountNumber]
        alt Session Valid (Success)
            Gateway-->>Client: Returns Encrypted Response (code="00")
            note over Client: Parse balance details
        else Session Expired / Stale (Failed)
            Gateway-->>Client: Returns Plain JSON Error (code="01", des="Something went wrong")
            note over Client: Raise SessionExpiredError<br/>Triggers fresh Login Flow (Step 1)
        end
    end
```

---

## 4. Query Flow (Balance & Profile)

Once the session token is set in the `Authorization` header, the client can query account details:

```mermaid
sequenceDiagram
    autonumber
    participant Client as Unofficial Client
    participant Gateway as api-ib.pgbank.com.vn
    
    rect rgb(240, 245, 255)
        note over Client, Gateway: Get Customer Info
        Client->>Gateway: POST /utility-service/8041<br/>[Headers: Auth=Session Token]
        Gateway-->>Client: Returns Encrypted Response<br/>[Payload: customer: {cifNo, fullName, address, gender}]
    end
    
    rect rgb(240, 245, 255)
        note over Client, Gateway: Get Accounts List
        Client->>Gateway: POST /bank-service/3004<br/>[Headers: Auth=Session Token]
        Gateway-->>Client: Returns Encrypted Response<br/>[Payload: data: [{accountNo, custName, availableBalance, currency, accountTypeName}]]
    end
```

---

## 5. Recipient Name Verification Flow

This flow resolves the recipient's full name given a target bank code and account/card number.

### A. Internal / CITAD Transfer (MID 5000)
Used when sending to another PGBank account or via standard interbank CITAD:
```mermaid
sequenceDiagram
    autonumber
    participant Client as Unofficial Client
    participant Gateway as api-ib.pgbank.com.vn
    
    Client->>Gateway: POST /bank-service/5000 (Get Receiver Name)<br/>[Headers: Auth=Session Token]<br/>[Encrypted Envelope: identifier (account), bankCode, beneficiaryName=""]
    Gateway-->>Client: Returns Encrypted Response (code="00")<br/>[Payload: beneficiaryName (e.g. "NGUYEN MINH SON")]
```

### B. NAPAS 24/7 Fast Transfer (MID 5009)
Used when resolving names for interbank 24/7 fast transfers by card or account number:
```mermaid
sequenceDiagram
    autonumber
    participant Client as Unofficial Client
    participant Gateway as api-ib.pgbank.com.vn
    
    Client->>Gateway: POST /bank-service/5009 (Get Receiver Name NAPAS)<br/>[Headers: Auth=Session Token]<br/>[Encrypted Envelope: identifier (account), bankCode, sourceAccount, beneficiaryName=""]
    Gateway-->>Client: Returns Encrypted Response (code="00")<br/>[Payload: beneficiaryName (e.g. "NGUYEN MINH SON")]
```

---

## 6. Password Change Flow (No OTP)

PGBank allows logged-in users to change their password using the old password, new password, and confirmation password, without sending an SMS OTP.

```mermaid
sequenceDiagram
    autonumber
    participant Client as Unofficial Client
    participant Gateway as api-ib.pgbank.com.vn
    
    Client->>Gateway: POST /auth-service/2001 (Change Password After Login)<br/>[Headers: Auth=Session Token]<br/>[Encrypted Envelope: oldPassword, newPassword, newPasswordVerify]<br/>(Note: newPasswordVerify must match newPassword)
    Gateway-->>Client: Returns Encrypted Response (code="00", des="Success")
    note over Client: Update client.password to the new password
```

---

## 7. Contact (Beneficiary) Management Flow

PGBank supports full CRUD operations on saved transfer contacts (beneficiaries).

### A. Fetch Contacts List (MID 8014)
```mermaid
sequenceDiagram
    autonumber
    participant Client as Unofficial Client
    participant Gateway as api-ib.pgbank.com.vn
    
    Client->>Gateway: POST /utility-service/8014 (Get Contacts)<br/>[Headers: Auth=Session Token]<br/>[Encrypted Envelope: beneType="1,2,3"]
    Gateway-->>Client: Returns Encrypted Response (code="00")<br/>[Payload: listContact: [{id, name, pan, beneName, bankCode, bankName, favourite, ...}]]
```

### B. Create Contact (MID 8015)
```mermaid
sequenceDiagram
    autonumber
    participant Client as Unofficial Client
    participant Gateway as api-ib.pgbank.com.vn
    
    Client->>Gateway: POST /utility-service/8015 (Create Contact)<br/>[Headers: Auth=Session Token]<br/>[Encrypted Envelope: name, pan, beneName, bankCode, bankName, beneType, favourite]
    Gateway-->>Client: Returns Encrypted Response (code="00")
```

### C. Update Contact (MID 8016)
Used to toggle favorite status or update the contact's nickname:
```mermaid
sequenceDiagram
    autonumber
    participant Client as Unofficial Client
    participant Gateway as api-ib.pgbank.com.vn
    
    Client->>Gateway: POST /utility-service/8016 (Update Contact)<br/>[Headers: Auth=Session Token]<br/>[Encrypted Envelope: beneId, name (optional), favourite (optional)]
    Gateway-->>Client: Returns Encrypted Response (code="00")
```

### D. Delete Contacts (MID 8017)
Supports single or bulk deletion via comma-separated ID lists:
```mermaid
sequenceDiagram
    autonumber
    participant Client as Unofficial Client
    participant Gateway as api-ib.pgbank.com.vn
    
    Client->>Gateway: POST /utility-service/8017 (Remove Contact)<br/>[Headers: Auth=Session Token]<br/>[Encrypted Envelope: beneIds (e.g. "123,456")]
    Gateway-->>Client: Returns Encrypted Response (code="00")
```

In the next chapter, we will go over educational notes, architectural patterns, and troubleshooting tips for maintaining unofficial client wrappers.
