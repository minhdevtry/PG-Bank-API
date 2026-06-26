# PGBank Unofficial Library — Phase 7-9 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement SQLite storage persistence for accounts and jobs, integrate Telegram/Discord webhooks, write VietQR tests, and prepare release packaging.

**Architecture:**
- **Pluggable Application Storage:** Define `BaseStorage` in `storage.py` and implement `SQLiteStorage` and `MemoryStorage`.
- **Database Persistence:** Save account details and scheduler job metadata (trigger, action serialization) to SQLite. Auto-run schema migrations on init.
- **Rich Webhook Dispatchers:** Implement specialized webhook integration helpers for Discord (embed payloads) and Telegram (Jinja2 text formatting).
- **Offline QR & Tests:** Complete unit tests for the offline-capable `VietQR` generator.

**Tech Stack:**
- Python 3.9+
- `sqlite3` (stdlib) for SQLite persistence
- `jinja2` for Telegram template rendering (optional dependency, handles import gracefully)
- `httpx` for Discord/Telegram HTTP POST requests
- `pytest` for unit testing

## Global Constraints

- **Public API exports**: All new classes/functions (e.g. `SQLiteStorage`, `BaseStorage`, `VietQR`, etc.) MUST be added to `src/pgbank_unofficial/__init__.py` AND to the `__all__` list.
- **Backward compatibility**: Do not change the signature of existing public methods unless extending them with default arguments.
- **Type hints**: All public functions and methods must have complete type annotations.
- **Tests required**: Each new code segment must be accompanied by robust unit tests. Aim for 80%+ test coverage.
- **Lint compliance**: `ruff check src/` and `black --check src/` must pass before completion.

---

### Task 7: SQLite Persistence & Storage Backend

**Files:**
- Modify: `src/pgbank_unofficial/storage.py`
- Modify: `src/pgbank_unofficial/manager.py`
- Modify: `src/pgbank_unofficial/scheduler.py`
- Create: `tests/test_manager_storage.py`

**Interfaces:**
- Produces: `BaseStorage`, `SQLiteStorage`, `MemoryStorage` classes in `storage.py`.
- Integrates `storage` argument into `PGBankManager` and `AutoPaymentScheduler`.

- [ ] **Step 1: Define storage interfaces in storage.py**

- [ ] **Step 2: Implement SQLiteStorage and MemoryStorage in storage.py**

- [ ] **Step 3: Integrate BaseStorage into PGBankManager**

Modify `src/pgbank_unofficial/manager.py` to:
1. Accept `storage: Optional[BaseStorage] = None` in `__init__`.
2. Default storage to `SQLiteStorage(Path.home() / ".pgbank_unofficial" / "data.db")`.
3. Read/write accounts database utilizing `storage`.
4. Close and update local lists.

- [ ] **Step 4: Integrate BaseStorage into AutoPaymentScheduler**

Modify `src/pgbank_unofficial/scheduler.py` to:
1. Fetch jobs and store runs in the manager's `storage`.
2. When creating jobs, tag action signatures to allow action reconstruction.
3. Automatically load persistent jobs on scheduler startup.

- [ ] **Step 5: Create tests/test_manager_storage.py and verify**

Verify SQLiteStorage save/load functionality.
Run: `pytest tests/test_manager_storage.py -v`

- [ ] **Step 6: Commit**

---

### Task 8: Webhook Discord/Telegram Integrations

**Files:**
- Modify: `src/pgbank_unofficial/webhook.py`
- Modify: `tests/test_webhook.py`

**Interfaces:**
- Exposes `register_discord()`, `register_telegram()`, and `register_webhook()` methods on `WebhookDispatcher`.

- [ ] **Step 1: Implement register_discord inside WebhookDispatcher**

- [ ] **Step 2: Implement register_telegram inside WebhookDispatcher**

- [ ] **Step 3: Write tests for Discord/Telegram webhook dispatching in tests/test_webhook.py**

- [ ] **Step 4: Run pytest on test_webhook.py and verify passing**

- [ ] **Step 5: Commit**

---

### Task 9: VietQR Tests, Package Setup, and Refactor

**Files:**
- Create: `tests/test_vietqr.py`
- Modify: `src/pgbank_unofficial/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write tests for VietQR in tests/test_vietqr.py**

Verify EMVCo payload format, CRC checksum, and image URL generation.

- [ ] **Step 2: Export new symbols in __init__.py**

Export `SQLiteStorage`, `BaseStorage`, `VietQR`, etc.

- [ ] **Step 3: Build & package check**

Run `python -m build` and `twine check dist/*` to verify package compliance.

- [ ] **Step 4: Commit**
