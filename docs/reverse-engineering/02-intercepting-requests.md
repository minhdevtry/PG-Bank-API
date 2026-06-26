# Chapter 2: Intercepting and Analyzing Requests

This chapter details how to intercept and trace the bootstrapping parameters, discover the API structure, analyze request headers, and map the routing system of PGBank's Omni Channel API.

---

## 1. The Bootstrapping Phase: `mount.json`

Before PGBank's client makes any API call, it must fetch its system configuration. This is fetched as a static JSON file:

* **URL**: `https://ib.pgbank.com.vn/assets/mount/mount.json`
* **Method**: `GET`
* **Authentication**: None

### Anatomy of `mount.json`
This file contains the configuration variables for the frontend app. Among standard configuration flags, there are three critical cryptographic keys:

```json
{
  "production": true,
  "baseUrl": "https://api-ib.pgbank.com.vn",
  "c2Vy78dmVyUHVibGljS2V522RGV71mYXVsdA": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAv...",
  "S23E1BQ45w": {
    "HMAC": "pgomni20250323"
  },
  "Z8GVm3Y2X3Vs11dFRva2Vu": "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOi..."
}
```

* **`baseUrl`**: The API Gateway base URL (usually `https://api-ib.pgbank.com.vn`).
* **Server RSA Public Key (`c2Vy...`)**: Base64-encoded RSA public key used to encrypt the symmetric session key for requests.
* **HMAC Config (`S23E1BQ45w` -> `HMAC`)**: Secret salt used to generate the checksum signature for login payloads.
* **Default Bearer Token (`Z8GV...`)**: Pre-shared JWT Bearer token used for anonymous requests (like fetching system status, configuration, or initiating login step 1 before a session ID exists).

> [!NOTE]
> The keys in `mount.json` are obfuscated with semi-random names (e.g., `Z8GVm3Y2X3Vs11dFRva2Vu` translates to `defaultToken` in Base64-like obfuscation). These keys change occasionally during frontend deployments. A robust API client should fetch and parse `mount.json` dynamically on startup instead of hardcoding these values.

---

## 2. API Routing Structure

PGBank organizes endpoints by service categories and message IDs (MIDs). The URL pattern is:

$$\text{URL} = \text{baseUrl} + \text{"/"} + \text{service} + \text{"/"} + \text{MID}$$

For example:
`https://api-ib.pgbank.com.vn/auth-service/1004`

Below is a map of the essential services and MIDs:

| Service Name | Description | Message ID (MID) | Endpoint Path | Function |
| :--- | :--- | :--- | :--- | :--- |
| `auth-service` | Authentication operations | `1004` | `/auth-service/1004` | Login Step 1 (Credential verification) |
| `auth-service` | Authentication operations | `1002` | `/auth-service/1002` | Login Step 2 (Confirm OTP) |
| `auth-service` | Authentication operations | `2001` | `/auth-service/2001` | Change Password (after login, no OTP required) |
| `utility-service` | Profile & configurations | `8041` | `/utility-service/8041` | Get Customer Info (CIF, full name, profile) |
| `utility-service` | Profile & configurations | `8014` | `/utility-service/8014` | Get Contacts (Beneficiary list) |
| `utility-service` | Profile & configurations | `8022` | `/utility-service/8022` | Get List Bank (NAPAS/CITAD supported banks) |
| `bank-service` | Account management | `3004` | `/bank-service/3004` | Get Payment Accounts (Checking accounts) |
| `bank-service` | Account management | `3008` | `/bank-service/3008` | Available Balance (Live balance fetch) |
| `bank-service` | Account management | `3005` | `/bank-service/3005` | Get Account Saving (Savings accounts list) |
| `bank-service` | Name Resolution / Transfers | `5000` | `/bank-service/5000` | Get Receiver Name (Internal / CITAD transfer lookup) |
| `bank-service` | Name Resolution / Transfers | `5009` | `/bank-service/5009` | Get Receiver Name NAPAS (24/7 fast transfer lookup) |
| `bank-service` | Transaction History | `3010` | `/bank-service/3010` | Get Transaction History (fromDate/toDate range query) |
| `bank-service` | Transaction History | `3012` | `/bank-service/3012` | Get Detail Transaction History |

---

## 3. Headers and Device Fingerprinting

Every request sent to the API Gateway must contain specific headers. If any are missing or malformed, the API Gateway rejects the request (often with HTTP 400 or HTTP 401).

```http
POST /bank-service/3004 HTTP/1.1
Host: api-ib.pgbank.com.vn
Connection: keep-alive
Content-Length: 1024
Accept: application/json, text/plain, */*
Authorization: Bearer eyJhbGciOiJIUzUxMiJ9...
x-request-id: 178220000000085c5cdf7af
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/145.0.0.0 Safari/537.36
Content-Type: application/json
Origin: https://ib.pgbank.com.vn
Referer: https://ib.pgbank.com.vn/
Accept-Encoding: gzip, deflate, br
Accept-Language: vi,en-US;q=0.9
```

### Key Headers Analysis

1. **`Authorization`**: 
   - Starts with `Bearer ` followed by a JWT.
   - Before logging in, this is the **Default Bearer Token** extracted from `mount.json`.
   - After a successful login, the server returns a user-specific token which replaces the default token for all subsequent requests.

2. **`x-request-id`**:
   - A unique correlation ID generated on the client for tracking and anti-replay defense.
   - **Format**: `13-digit-timestamp` + `8-character-suffix`
     - Example: `1782200000000` (timestamp in ms) + `85c5cdf7af` (suffix).
     - The suffix is a client fingerprint, often derived from device parameters or generated statically on initialization.

3. **`Origin` & `Referer`**:
   - Strict CORS policy requires these headers to match the official domain `https://ib.pgbank.com.vn`.

---

## 4. The Payload Wrapper Format

All requests and responses (except public assets and `mount.json`) are wrapped in an envelope containing encrypted contents. You will never see raw JSON parameters like `{"username": "..."}` or `{"balance": 1000}` in proxy logs.

### Request Body Format
```json
{
  "k": "d1/V0Z5Jd...[~344 chars of Base64]...",
  "d": "A9+z8XvB...[~500+ chars of Base64]..."
}
```

* **`k`**: The **Encrypted Symmetric Key**. It contains the AES key and IV generated by the client, encrypted using the server's RSA Public Key.
* **`d`**: The **Encrypted Data Payload**. It contains the actual JSON request parameters encrypted using the client-generated AES key and IV in GCM (or CBC) mode.

### Response Body Format
For successful transactions, the server responds with a raw string (instead of a JSON object) containing the ciphertext:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

WjRkaDlz...[Raw Base64 Ciphertext]...
```

* The client decrypts this raw response body using the **same** AES key and IV it generated for the request.
* For failed Gateway requests (e.g. invalid tokens), the server might respond with standard unencrypted JSON error logs (e.g. `{"code": "01", "des": "Something went wrong"}`). Your client must support parsing both plain JSON and decrypted text formats.

In the next chapter, we will explain the cryptography mechanics and walk through how to decrypt and encrypt these payloads.
