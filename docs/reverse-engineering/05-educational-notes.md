# Chapter 5: Architectural Notes & Best Practices

This concluding chapter outlines critical takeaways, troubleshooting scenarios, and security recommendations for maintaining and extending the unofficial PGBank library.

---

## 1. Key Lessons Learned

### A. Dynamic Bootstrapping is Critical
The keys, salts, and endpoints of the PGBank portal change regularly during application deployments. Hardcoding keys like the server public key or the default Bearer token will cause the client to break.
* **Solution**: The client fetches `mount.json` dynamically on startup, automatically parsing the obfuscated fields (`c2Vy...` and `Z8GV...`).

### B. Device Fingerprint Binding (`browserId`)
PGBank ties active sessions to the `browserId` used during authentication. If you authenticate with `browserId_A` and try to reuse the session token on `browserId_B`, the server immediately terminates the session with `Something went wrong`.
* **Solution**: Keep `browserId` persistent across session saving and loading. If running multi-account operations, assign a unique `browserId` to each account.

### C. Handshaking Custom Headers
The server validates the `x-request-id` format. If the format does not match the timestamp + CRC-16-CCITT(username) + client ID suffix, the gateway blocks the request before it even reaches the authentication handler.
* **Solution**: The custom CRC-16 generation function binds each request ID to the logged-in username, mirroring the browser client's behavior.

### D. Pre-Login OTP Verification & `userName` Requirement
During the initial pre-login state, the `Authorization` header carries a default, shared Bearer token.
* **Problem**: Because this token is the same for all users, the bank's backend API gateway does not know *which* account's OTP token (`otpToken` / `txnToken`) is being verified during step 2 (`CONFIRM_OTP` / `1002`).
* **Solution**: The `userName` (phone number) parameter must be explicitly passed in the encrypted JSON payload of the confirmation step, even though it was already supplied in the login request. Failing to include it results in `Token không hợp lệ` (code "01"). Additionally, SMS OTPs are valid for exactly **60 seconds**, requiring immediate execution.

### E. Multi-Account Management & Isolation
When managing multiple accounts concurrently:
1. **Isolated Session Storage**: Save session files separately per-account (e.g., using `PGBankManager` which writes to `{nickname}.json`, or using a database schema with `account_id` as primary key).
2. **Distinct Browser IDs**: Never share a single browser ID or hardware fingerprint between multiple accounts. Generate a unique `browserId` for each account on first login and persist it alongside that account's session.
3. **Per-Account Proxy Isolation**: Use distinct HTTP proxies for each client instance to distribute requests across multiple IPs. This avoids rate-limiting, concurrent-session warnings, and automated risk triggers on the banking gateway.

---

## 2. Dealing with OTP Challenges

To prevent manual OTP inputs in automated systems (like SMS-forwarding networks):
1. **Re-use Existing Sessions**: The session token, RSA keys, and browser ID can be serialized and saved to a local file. As long as the session is refreshed before expiry, the client never needs to prompt for OTP again.
2. **Automated OTP Reading**: By passing an `otp_provider` callback to the client constructor, developers can hook into SMS forwarding APIs, email monitors, or terminal prompts:
   ```python
   def fetch_from_sms_gateway(prompt_text):
       # Hit an SMS listener server to grab the latest verification code
       return my_sms_server.get_latest_otp(for_number="<account_phone>")

   client = PGBankClient(
       username="...", password="...", browser_id="...",
       otp_provider=fetch_from_sms_gateway
   )
   ```

3. **Pluggable Session Storage**: Session tokens can be persisted to **any** storage backend by implementing the `BaseSessionStorage` interface. The library ships with three ready-to-use backends (`FileSessionStorage`, `DirSessionStorage`, `MemorySessionStorage`); user code can supply anything else (SQLite, PostgreSQL, Redis, Supabase, AWS Secrets Manager, etc.) by overriding three methods. This keeps the library free of hardcoded storage assumptions and lets each project choose the persistence layer that matches its deployment topology.

---

## 3. Resiliency: Circuit Breakers and Retries

Banking APIs can be highly rate-limited or experience transient gateway dropouts. If the client hammers the API during a outage, it risks blocking the user account.
* **Circuit Breaker**: In `http.py`, a circuit breaker pattern is implemented. If the API returns consecutive transport errors (e.g. DNS failure, connection timeouts), the circuit opens and blocks further requests immediately to protect credentials, resetting only after a cooldown period.
* **Thread-Safety & Multi-Account Execution**: Using the `PGBankManager` interface, developers can run queries across multiple accounts concurrently, using isolation boundaries to ensure a failure on one account does not impact others.

---

## 4. Troubleshooting Reference

### Error: `Something went wrong` (Code "01", MsgCode "96")
This is a catch-all gateway error message. It usually indicates one of the following:
1. **Session Expired**: The session token has timed out (default timeout is ~15-30 minutes of inactivity).
2. **Cryptographic Mismatch**: The AES key decryption failed on the server side because the wrong Server RSA Public Key was used.
3. **Invalid Request Signature**: The `checkSum` in the login payload did not match the HMAC signature.

### Error: `Security Violation`
This is triggered if the request headers are missing `Origin` or `Referer`, or if the `x-request-id` header is missing/malformed.

---

## 5. Guide for Future Developers & AI Agents

When building wrappers for other Vietnamese banks (like Vietcombank, Techcombank, BIDV), follow this reverse engineering framework:
1. **Trace Assets**: Look for config files like `config.json`, `mount.json`, or environment variables injected in JS bundles (inspecting `main.js` via DevTools).
2. **Map Encryption**: Check if payloads are sent as raw JSON or encrypted blobs. If encrypted, search JS bundles for keywords like `CryptoJS`, `encrypt`, `decrypt`, `Forge`, `RSA`, or `AES`.
3. **Isolate Signature Fields**: Identify if payloads require dynamic hashes (like checksums, sign keys, MD5/SHA hashes). Look for string concatenation formats.
4. **Implement Session Exporters**: Allow sessions to be written to disk so they can be loaded instantly without re-authenticating, minimizing OTP friction.
