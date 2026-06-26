# Chapter 3: Cryptography & Payload Encryption

PGBank API employs a **Hybrid Cryptography System** at the application layer. All requests and responses are wrapped inside encrypted envelopes to prevent eavesdropping and modification, even if an attacker manages to intercept the TLS/SSL layer.

This chapter details the math, formats, and algorithms used, complete with equivalent Python code snippets.

---

## 1. Cryptographic Specifications

| Component | Algorithm | Purpose |
| :--- | :--- | :--- |
| **Asymmetric Key Exchange** | RSA (1024-bit key size) with PKCS#1 v1.5 padding | Used to securely exchange the ephemeral symmetric key from client to server (parameter `k`). |
| **Symmetric Encryption** | AES-CTR (Counter mode) with a 32-byte (256-bit) key | Used to encrypt the actual JSON payload body (parameter `d`). |
| **Authentication/Checksum** | HMAC-SHA256 with pre-shared salt | Used to sign credential properties on login step 1 to prevent tampering. |
| **Fingerprint Generation** | Custom CRC-16 (CCITT-FALSE) | Used in the `x-request-id` header to bind requests to a specific username. |

---

## 2. The Hybrid Encryption Sequence

Every time a client makes an API call, it executes the following sequence:

```
[Client]                                                          [Server]
   │                                                                 │
   ├─► 1. Generate 32-byte AES Key & 16-byte IV                      │
   │                                                                 │
   ├─► 2. Encrypt AES Key with Server RSA Public Key (PKCS1v15)      │
   │      ===> Parameter "k" (Base64)                                │
   │                                                                 │
   ├─► 3. Encrypt JSON Payload with AES Key + IV (AES-CTR)           │
   │      ===> Parameter "d" (Base64 of IV + Ciphertext)             │
   │                                                                 │
   ├─► 4. Send POST {"k": k, "d": d} ───────────────────────────────►│
   │                                                                 │ (Decrypt k using RSA Private Key)
   │                                                                 │ (Decrypt d using AES-CTR)
   │                                                                 │ (Process & Generate response JSON)
   │                                                                 │ (Encrypt response JSON using same AES Key)
   │                                                                 │
   │◄─5. Return raw encrypted ciphertext ────────────────────────────┤
   │                                                                 │
   ├─► 6. Decrypt ciphertext using same AES Key & IV                 │
   ▼                                                                 ▼
```

### Request Wrapping Format

The raw JSON payload before encryption is structured as follows:

```json
{
  "clientPubKey": "Stripped PEM format of Client's public RSA key",
  "param1": "value1",
  "param2": "value2"
}
```

* **Client Key Generation**: During initialization, the client generates a unique ephemeral 1024-bit RSA keypair. It includes its public key in every request so the server can encrypt the response symmetric key.
* **Payload Encryption**: The client generates a random 32-byte AES key and 16-byte IV. It encrypts the merged JSON payload using AES-CTR.
* **Symmetric Envelope (`d`)**: The client prepends the 16-byte IV to the ciphertext, then Base64-encodes the entire string.
* **Key Envelope (`k`)**: The client encodes its AES key as a Base64 string, then encrypts that string using the Server's RSA Public Key with PKCS#1 v1.5 padding. The final result is Base64-encoded.

---

## 3. Python Implementation: Request Encryption

Here is a simplified Python representation using the `cryptography` library:

```python
import base64
import os
import json
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

def encrypt_payload(data: dict, client_pub_key: str, server_pub_key_b64: str) -> dict:
    # 1. Generate ephemeral key & IV
    aes_key = os.urandom(32)
    iv = os.urandom(16)
    
    # 2. Add client public key to the payload
    payload = {"clientPubKey": client_pub_key, **data}
    plaintext = json.dumps(payload).encode("utf-8")
    
    # 3. Symmetric AES-CTR encryption
    cipher = Cipher(algorithms.AES(aes_key), modes.CTR(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()
    
    # 4. Pack IV + Ciphertext as 'd'
    d_base64 = base64.b64encode(iv + ciphertext).decode()
    
    # 5. Encrypt AES Key with Server RSA Public Key as 'k'
    server_pem = base64.b64decode(server_pub_key_b64).decode()
    server_key = serialization.load_pem_public_key(server_pem.encode())
    
    encrypted_key = server_key.encrypt(
        base64.b64encode(aes_key),
        padding.PKCS1v15()
    )
    k_base64 = base64.b64encode(encrypted_key).decode()
    
    return {"d": d_base64, "k": k_base64}
```

---

## 4. Python Implementation: Response Decryption

Decryption reverses the wrapping sequence:
1. Decode the response envelope parameters (`k` and `d`) from Base64.
2. Decrypt `k` using the client's private RSA key to recover the AES key.
3. Slice the first 16 bytes of `d` as the IV, and the rest as the ciphertext.
4. Decrypt the ciphertext using AES-CTR with the recovered AES key and IV.

```python
def decrypt_response(enc_obj: dict, client_private_key_pem: str) -> dict:
    # If the gateway returned an unencrypted error (plain JSON)
    if "k" not in enc_obj or "d" not in enc_obj:
        return enc_obj

    # 1. Decode envelopes
    k_encrypted = base64.b64decode(enc_obj["k"])
    d_packed = base64.b64decode(enc_obj["d"])

    # 2. Decrypt symmetric AES key
    private_key = serialization.load_pem_private_key(
        client_private_key_pem.encode(), password=None
    )
    aes_key_b64 = private_key.decrypt(k_encrypted, padding.PKCS1v15())
    aes_key = base64.b64decode(aes_key_b64)

    # 3. Unpack IV and Ciphertext
    iv = d_packed[:16]
    ciphertext = d_packed[16:]

    # 4. Decrypt payload
    cipher = Cipher(algorithms.AES(aes_key), modes.CTR(iv))
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    return json.loads(plaintext.decode("utf-8"))
```

---

## 5. Login Signature (HMAC Checksum)

In addition to payload encryption, the Login request (`auth-service/1004`) requires a checksum signature parameter named `checkSum` inside the payload. 

The signature is computed over a `|`-separated concatenation of key credentials:

$$\text{data} = \text{username} + \text{"|"} + \text{password} + \text{"|"} + \text{browserId} + \text{"|"} + \text{requestTime}$$

* **HMAC Secret Key**: Loaded dynamically from `mount.json` under `mount["S23E1BQ45w"]["HMAC"]` (e.g. `pgomni20250323`).
* **Algorithm**: HMAC-SHA256.

```python
import hmac
import hashlib

def calculate_checksum(username, password, browser_id, request_time, hmac_key):
    msg = f"{username}|{password}|{browser_id}|{request_time}".encode("utf-8")
    signature = hmac.new(
        hmac_key.encode("utf-8"),
        msg,
        hashlib.sha256
    ).hexdigest()
    return signature
```

In the next chapter, we will visualize the sequence of operations for authentication (OTP, device validation) and query processing.
