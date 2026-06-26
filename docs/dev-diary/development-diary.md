# Development Diary & Change Log

This document records the architectural decisions, code changes, and bug fixes applied during the development of **pgbank-unofficial**.

---

## 📅 June 23, 2026: Phase 2 — Transaction History Module

### Features Added
1. **`history.py` — Transaction History API**:
   - `HistoryQuery` dataclass with optional filter fields: `account_number`, `from_date`, `to_date`, `min_amount`, `max_amount`, `direction`, `counterparty` (fuzzy), `description_search`, `category`
   - `HistoryQuery.__post_init__` validation: `min_amount > max_amount` and `from_date > to_date` raise `ValueError`
   - `TransactionHistory.query()`: wraps `client.get_transaction_history()`, applies filters in-memory (amount, direction, counterparty fuzzy match, description search, category)
   - `TransactionHistory.search()`: case-insensitive substring search across description, counterparty_name, counterparty_account; sorts by timestamp descending
   - `TransactionHistory.categorize()`: applies `{keyword: category_name}` rules (case-insensitive, first-match wins, default "Uncategorized")
   - `CategorizedTransaction` dataclass extends `Transaction` with `category` field
   - `query_all_accounts()`: parallel fetch across all `PGBankManager` accounts using `ThreadPoolExecutor`
   - `export_to_csv()`: uses stdlib `csv`, writes all standard columns + category
   - `export_to_json()`: writes valid JSON array
   - `export_to_excel()`: uses `openpyxl` (requires `pip install openpyxl`); raises `ImportError` with install hint if not available; formatted with header style + auto-sized columns

### Technical Notes
- No new runtime dependencies (openpyxl is optional)
- `query_all_accounts` uses `ThreadPoolExecutor` for concurrency (max_workers=4 default)
- All monetary values use `Decimal` (no float)
- Full async parity deferred (sync-only for Phase 2)

### Quality
- **31 new tests** added in `tests/test_history.py`
- **160/160 total tests passing** ✅
- ruff clean, black formatted, mypy clean
- Public API: all symbols exported from `pgbank_unofficial.__init__`

---

## 📅 June 23, 2026: Phase 1.2 — Contact Management & Transaction Queries

### Features Added
1. **Saved Contacts Query (`get_contacts`)**:
   - Queries saved beneficiaries list (MID `8014` on `utility-service`) using payload `{"beneType": "1,2,3"}`.
2. **Contact CRUD Management (`create_contact`, `update_contact`, `delete_contact`)**:
   - `create_contact` (MID `8015` on `utility-service`): Adds a new beneficiary with name, pan, bankCode, bankName, beneType, and favourite flag.
   - `update_contact` (MID `8016` on `utility-service`): Updates nickname (name) and favourite status of a beneficiary.
   - `delete_contact` / `remove_contact` (MID `8017` on `utility-service`): Supports single or bulk deletion of beneficiaries via comma-separated ID lists.
3. **Supported Banks List (`get_banks`)**:
   - Queries NAPAS/CITAD supported banks list (MID `8022` on `utility-service`).
4. **Dynamic Beneficiary Name Verification**:
   - `get_receiver_name`: Resolves recipient name for domestic/CITAD or PGBank accounts (MID `5000` on `bank-service`).
   - `get_receiver_name_napas`: Resolves recipient name for NAPAS 24/7 fast transfers (MID `5009` on `bank-service`).
5. **Transaction History Queries**:
   - `get_transaction_history`: Queries records in a date range (MID `3010` on `bank-service`) and parses them into `Transaction` dataclass objects.
   - `get_transaction_detail`: Fetches detailed logs for a specific transaction (MID `3012` on `bank-service`).

### Technical Fixes & Improvements
* **Active Session Expiry Check**:
   - Observed that the live API returns `"code": "98", "des": "Expire key"` when encryption/session keys expire.
   - Updated the sync and async clients' `_post` methods to catch `"code": "98"` or `"99"` and raise `SessionExpiredError`. This enables `is_alive()` to catch the exception, trigger `logout()`, log in fresh, and retry automatically.
* **Async Client Routing Correction**:
   - Fixed a bug where `AsyncPGBankClient` was hardcoded to use `_default_server_pubkey` for all requests. It now correctly dynamically routes requests to the account-specific `server_pubkey` for authenticated MIDs, matching the sync client.
* **Added Missing Properties**:
   - Added `self.account_no` to `AsyncPGBankClient` constructor to keep properties identical to `PGBankClient`.

---

## 📅 June 23, 2026: Phase 1.1 — Health Checks, Multi-Account, & VietQR

### Features Added
1. **Account Alive Check (`is_alive`)**:
   - Added active session checks for sync and async clients by fetching accounts list.
2. **Multi-Account Orchestrator (`PGBankManager`)**:
   - Coordinates multiple accounts with concurrent status checks and isolated parameters.
3. **EMVCo VietQR Standard (`vietqr.py`)**:
   - Generates static and dynamic QR strings according to NAPAS/EMVCo standard, creates terminal/PNG QR representations, and parses raw QR payloads.
4. **Live Verification**:
   - Successfully authenticated and verified balance queries against the live PGBank API.

---

## 📅 June 22-23, 2026: Phase 1 — Project Foundation

### Deliverables
1. **Hybrid Cryptography Wrapper (`_algorithm.py`)**:
   - Implemented RSA-PKCS1v15 symmetric key exchange wrapping and AES-CTR symmetric request/response body encryption.
2. **HTTP Transport Layer (`http.py`)**:
   - Handled proxy forwarding, HTTP client pooling, and implemented a **Circuit Breaker** to protect against client rate limits.
3. **Public Client APIs (`client.py` & `async_client.py`)**:
   - Auth flows, credentials checking, session persistence to local JSON files, and clean context managers.
