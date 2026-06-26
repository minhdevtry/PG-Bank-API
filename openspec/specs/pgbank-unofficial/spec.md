# PGBank Unofficial Library — OpenSpec

## Purpose

`pgbank-unofficial` là một Python library chính thức phát hành trên PyPI giúp developers tích hợp với PGBank API một cách dễ dàng, an toàn và có nhiều tính năng production-ready. Thư viện hỗ trợ:

- **Multi-account management** với proxy/BrowserID linh hoạt per-account
- **Auto-payment scheduling** (flagship) — lập lịch chuyển khoản định kỳ, hỗ trợ cron/interval/conditional triggers
- **Transaction history** với query nâng cao, categorization, export Excel/CSV/JSON
- **Webhook dispatcher** để tích hợp với Discord, Telegram, custom HTTP endpoints
- **Real-time monitoring** cho balance threshold alerts và transaction detection
- **Sync + Async API** song song cho scripts lẫn FastAPI web apps
- **CLI tool** cho non-coders

Library hướng tới là **de-facto standard** cho mọi ai muốn tự động hoá ngân hàng PGBank bằng Python.

---

## Requirements

### Requirement: Authentication & Session Management

The library SHALL authenticate users against PGBank's web API using credentials and a pre-obtained BrowserID, and SHALL persist session tokens to disk so subsequent calls do not require re-authentication until the session expires.

#### Scenario: First-time login with credentials

- **WHEN** user calls `client.login(username="alice", password="xxx", browser_id="bid_xxx")` on a fresh session
- **THEN** library SHALL perform `login_step1` and return an `AuthResult` indicating OTP is required
- **AND** library SHALL return `otp_ref` and `otp_token` for the user to submit OTP

#### Scenario: Complete login with OTP

- **WHEN** user calls `client.login(otp="123456")` after receiving the OTP challenge
- **THEN** library SHALL call `login_step2` with the OTP and stored `otp_ref`/`otp_token`
- **AND** library SHALL persist the resulting session to disk
- **AND** all subsequent API calls SHALL use the persisted session

#### Scenario: Auto-restore session on startup

- **WHEN** library starts with a valid session file on disk
- **THEN** library SHALL skip login and load the existing session
- **AND** library SHALL verify session validity with a lightweight API call (e.g., `get_customer_info`)
- **IF** session is expired, THEN library SHALL automatically re-login if credentials are available, ELSE raise `SessionExpiredError`

#### Scenario: BrowserID is mandatory

- **WHEN** user creates `PGBankClient` or `Account` without `browser_id`
- **THEN** library SHALL raise `MissingBrowserIDError` immediately

---

### Requirement: Multi-Account Management

The library SHALL support managing multiple PGBank accounts simultaneously, each with its own credentials, optional proxy, and BrowserID configuration.

#### Scenario: Add accounts with shared BrowserID and different proxies

- **WHEN** user adds 2 accounts both using `browser_id="bid_shared"` but different `proxy` URLs
- **THEN** library SHALL store both accounts and create separate HTTP clients per account
- **AND** each account SHALL use its own proxy when making API calls

#### Scenario: Add accounts with unique BrowserIDs and shared proxy

- **WHEN** user adds 2 accounts with different `browser_id`s but the same `proxy`
- **THEN** library SHALL create separate HTTP clients
- **AND** both accounts SHALL route through the shared proxy

#### Scenario: Add accounts without proxy

- **WHEN** user adds an account with `proxy=None`
- **THEN** library SHALL make API calls directly without proxy

#### Scenario: Bulk query all accounts

- **WHEN** user calls `manager.get_all_balances()`
- **THEN** library SHALL query balance for all registered accounts in parallel (with rate limiting)
- **AND** library SHALL return `dict[account_id, Balance]`

#### Scenario: Health check

- **WHEN** user calls `manager.health_check()`
- **THEN** library SHALL attempt lightweight API call on each account
- **AND** library SHALL return `dict[account_id, AccountStatus]` (ALIVE / LOCKED / OTP_REQUIRED / ERROR)

#### Scenario: Per-account credential update

- **WHEN** user calls `manager.update_account(account_id, proxy="http://new:8080")`
- **THEN** library SHALL update the stored configuration
- **AND** subsequent API calls SHALL use the new proxy

---

### Requirement: Account & Balance Queries

The library SHALL expose typed methods to query account information and balances.

#### Scenario: Get customer info

- **WHEN** user calls `client.get_customer_info()`
- **THEN** library SHALL return an `AccountInfo` dataclass with `customer_id`, `customer_name`, `accounts` (list of `BankAccount`), and `primary_account`

#### Scenario: Get balance for default account

- **WHEN** user calls `client.get_balance()`
- **THEN** library SHALL return `Balance(account_number, available, total, currency, as_of)`

#### Scenario: Get balance for specific account

- **WHEN** user calls `client.get_balance(account_number="1234567890")`
- **THEN** library SHALL return the balance for that specific account

#### Scenario: Decimal precision

- **WHEN** any monetary value is returned
- **THEN** library SHALL use `decimal.Decimal` type (never float) to avoid precision loss

---

### Requirement: Transfer Operations

The library SHALL support 3 types of transfers: domestic (intra-PGBank), NAPAS (inter-bank domestic), CITAD (inter-bank with CITAD network), and same-owner.

#### Scenario: Domestic transfer

- **WHEN** user calls `client.transfer(from_account="123", to_account="456", amount=100000, bank_code="PGBANK")`
- **THEN** library SHALL perform init → verify → confirm flow
- **AND** library SHALL return `TransferResult(success=True, txn_id, timestamp, fee)`

#### Scenario: NAPAS transfer

- **WHEN** user calls `client.transfer(...)` with a non-PGBank `bank_code` (e.g., Vietcombank)
- **THEN** library SHALL use the NAPAS transfer endpoints (init_napas/verify_napas/confirm_napas)

#### Scenario: Transfer requires OTP

- **WHEN** PGBank API responds with "OTP_REQUIRED" during verify step
- **AND** user has set `otp_callback` on the client
- **THEN** library SHALL call `otp_callback(prompt)` and wait for OTP string
- **AND** library SHALL retry verify with the provided OTP

#### Scenario: Dry-run transfer

- **WHEN** user calls `client.transfer(..., dry_run=True)`
- **THEN** library SHALL perform init + verify steps but NOT confirm
- **AND** library SHALL return `TransferResult(success=True, dry_run=True, ...)` with simulated confirmation

#### Scenario: Lookup recipient

- **WHEN** user calls `client.lookup_recipient(account="1234567890", bank_code="PGBANK")`
- **THEN** library SHALL return the recipient's full name as a string
- **AND** library SHALL cache the result for 24 hours

---

### Requirement: Transaction History

The library SHALL query, filter, search, categorize, and export transaction history across one or multiple accounts.

#### Scenario: Query history with filters

- **WHEN** user calls `history.query(HistoryQuery(from_date=..., to_date=..., min_amount=1000000))`
- **THEN** library SHALL return `list[Transaction]` matching all specified filters

#### Scenario: Search transactions

- **WHEN** user calls `history.search("GRAB", account="alice")`
- **THEN** library SHALL perform fuzzy match on description, counterparty name, and counterparty account
- **AND** return matching transactions

#### Scenario: Auto-categorization

- **WHEN** user calls `history.categorize(transactions)` after adding rules like `"GRAB" -> "Di chuyển"`
- **THEN** library SHALL apply rules to each transaction
- **AND** return `list[CategorizedTransaction]` with `category` field populated

#### Scenario: Export to Excel

- **WHEN** user calls `export_to_excel(transactions, output_path="report.xlsx")`
- **THEN** library SHALL write a formatted Excel file with columns: Date, Account, Direction, Amount, Counterparty, Description, Category

#### Scenario: Multi-account history aggregation

- **WHEN** user calls `history.query_all_accounts(query)`
- **THEN** library SHALL fetch transactions from all registered accounts
- **AND** return `dict[account_id, list[Transaction]]`

---

### Requirement: Auto-Payment Scheduling (FLAGSHIP)

The library SHALL provide a scheduler to automate recurring, one-time, or conditional transfers.

#### Scenario: Add a cron-scheduled job

- **WHEN** user calls `scheduler.add_job(Job(name="...", trigger=CronTrigger("0 9 5 * *"), action=...))`
- **THEN** library SHALL persist the job to storage
- **AND** library SHALL compute `next_run_at` based on the cron expression

#### Scenario: Job executes on schedule

- **WHEN** the trigger fires (e.g., it's 9 AM on the 5th of the month)
- **THEN** library SHALL execute the action callable in a thread pool
- **AND** library SHALL record the run (success/failure, timestamp, error) to `job_history`

#### Scenario: Interval trigger with jitter

- **WHEN** user creates `IntervalTrigger(days=1, jitter_seconds=600)`
- **THEN** library SHALL add random 0-600 second delay to each fire time
- **AND** library SHALL log the actual fire time for audit

#### Scenario: Conditional trigger

- **WHEN** user creates `ConditionalTrigger(check_every=timedelta(hours=6), condition=lambda c: c.get_balance().available > 50000000)`
- **THEN** library SHALL poll the condition every 6 hours
- **AND** execute the action when condition returns True

#### Scenario: Pause and resume a job

- **WHEN** user calls `scheduler.pause_job(job_id)`
- **THEN** library SHALL mark the job as paused
- **AND** the trigger SHALL NOT fire until resumed

#### Scenario: Auto-pause after repeated failures

- **WHEN** a job fails 3 consecutive times (configurable threshold)
- **THEN** library SHALL automatically pause the job
- **AND** library SHALL dispatch a `JobEvent` notification via the WebhookDispatcher

#### Scenario: Manual run

- **WHEN** user calls `scheduler.run_job_now(job_id)`
- **THEN** library SHALL execute the job immediately, bypassing the trigger
- **AND** return the `JobRun` result

#### Scenario: Dry-run mode

- **WHEN** user creates `Job(..., dry_run=True)`
- **THEN** library SHALL execute the action in dry-run mode
- **AND** no actual transfer SHALL be performed

#### Scenario: OTP callback for transfers

- **WHEN** a transfer job requires OTP
- **THEN** library SHALL call `scheduler.otp_callback(job, prompt)`
- **AND** wait for the returned OTP string

#### Scenario: Daily limit safety

- **WHEN** a job would cause total transfers in a day to exceed `daily_limit_per_account` (configurable, default 50M VND)
- **THEN** library SHALL refuse to execute and log a warning
- **AND** mark the job run as `failed` with reason `DAILY_LIMIT_EXCEEDED`

#### Scenario: Job history persistence

- **WHEN** library restarts
- **THEN** all jobs and their run history SHALL be reloaded from SQLite
- **AND** any jobs that were due during downtime SHALL fire immediately on restart (with jitter)

---

### Requirement: Webhook Dispatcher

The library SHALL dispatch events (BalanceEvent, TransactionEvent, JobEvent) to registered subscribers and HTTP endpoints with retry logic.

#### Scenario: Register Discord webhook

- **WHEN** user calls `dispatcher.register_discord(webhook_url, events=[TransactionEvent])`
- **THEN** library SHALL send a POST to the Discord URL whenever a TransactionEvent fires
- **AND** format the payload as a Discord embed message

#### Scenario: Register Telegram bot

- **WHEN** user calls `dispatcher.register_telegram(bot_token, chat_id, events=[BalanceEvent], template="...")`
- **THEN** library SHALL send the templated message via Telegram Bot API
- **AND** Jinja2 template variables SHALL be filled with event fields

#### Scenario: HMAC signing for custom webhooks

- **WHEN** user calls `dispatcher.register_webhook(url, secret="my-secret", ...)`
- **THEN** library SHALL include `X-PGBank-Signature` header with HMAC-SHA256(payload, secret)

#### Scenario: Retry on failure

- **WHEN** webhook delivery fails (non-2xx response or timeout)
- **THEN** library SHALL retry with exponential backoff (default: 2s, 4s, 8s, 16s, 32s)
- **AND** after max_retries (default 5), mark as `failed`

#### Scenario: In-process callback subscription

- **WHEN** user calls `dispatcher.subscribe(TransactionEvent, my_async_func)`
- **THEN** library SHALL call `my_async_func(event)` whenever a TransactionEvent fires

---

### Requirement: Real-Time Monitoring

The library SHALL poll balances and transactions at user-defined intervals and dispatch events when changes are detected.

#### Scenario: Balance polling

- **WHEN** user starts `BalancePoller(poll_interval=timedelta(minutes=5))`
- **THEN** library SHALL fetch balance for each account every 5 minutes
- **AND** dispatch `BalanceEvent` when balance changes by more than 1000 VND (configurable threshold)

#### Scenario: Transaction polling

- **WHEN** user starts `TransactionMonitor(poll_interval=timedelta(minutes=2))`
- **THEN** library SHALL fetch new transactions since last poll
- **AND** dispatch `TransactionEvent` for each new transaction

#### Scenario: Threshold alert

- **WHEN** user calls `poller.alert_below(account_id, amount=100000)`
- **THEN** library SHALL dispatch a custom event when balance drops below 100000 VND

---

### Requirement: CLI Tool

The library SHALL provide a `pgbank` CLI for command-line usage without writing Python code.

#### Scenario: Add account via CLI

- **WHEN** user runs `pgbank account add --username alice --password xxx --browser-id bid_xxx [--proxy ...] [--nickname ...]`
- **THEN** library SHALL persist the account to the default storage
- **AND** print a success message

#### Scenario: Query balance via CLI

- **WHEN** user runs `pgbank balance [--account alice]`
- **THEN** library SHALL print a formatted table of balances

#### Scenario: Schedule a job via CLI

- **WHEN** user runs `pgbank schedule add --name "..." --cron "..." --account ... --to ... --amount ...`
- **THEN** library SHALL create a scheduled job and persist it

#### Scenario: JSON output mode

- **WHEN** user runs any `pgbank` command with `--json`
- **THEN** library SHALL output the result as JSON (for scripting)

---

### Requirement: Storage Abstraction

The library SHALL persist all state (accounts, jobs, job history, cached data) to SQLite by default, and SHALL support swapping to alternative backends.

#### Scenario: Default SQLite storage

- **WHEN** user creates `PGBankManager()` without specifying storage
- **THEN** library SHALL use SQLite at `~/.pgbank_unofficial/data.db`

#### Scenario: Custom storage path

- **WHEN** user creates `PGBankManager(storage=SQLiteStorage(path="/custom/path.db"))`
- **THEN** library SHALL store all data at the custom path

#### Scenario: Schema migrations

- **WHEN** library version is upgraded
- **THEN** library SHALL automatically apply any pending schema migrations on startup

---

### Requirement: Async API

The library SHALL provide full async equivalents of all sync APIs.

#### Scenario: Async login

- **WHEN** user calls `await async_client.login(...)`
- **THEN** library SHALL perform authentication without blocking the event loop

#### Scenario: Async transfer

- **WHEN** user calls `await async_client.transfer(...)`
- **THEN** library SHALL execute the transfer flow asynchronously

#### Scenario: Async scheduler

- **WHEN** user starts `AsyncAutoPaymentScheduler`
- **THEN** library SHALL use `asyncio` for job execution and trigger evaluation
- **AND** be safe to use in FastAPI/Starlette applications

---

### Requirement: Error Handling

The library SHALL raise specific, typed exceptions for different failure modes.

#### Scenario: Authentication failure

- **WHEN** PGBank API rejects credentials
- **THEN** library SHALL raise `AuthenticationError` with reason

#### Scenario: Session expired

- **WHEN** API call fails with `SESSION_EXPIRED` error code
- **THEN** library SHALL attempt re-login (if credentials are available) or raise `SessionExpiredError`

#### Scenario: Network timeout

- **WHEN** API call exceeds the configured timeout (default 30s)
- **THEN** library SHALL raise `TimeoutError`
- **AND** retry policy (if enabled) SHALL be applied

#### Scenario: Rate limit

- **WHEN** PGBank API returns HTTP 429
- **THEN** library SHALL respect `Retry-After` header
- **AND** apply circuit breaker if sustained

---

### Requirement: Logging & Observability

The library SHALL emit structured logs at appropriate levels.

#### Scenario: Login logging

- **WHEN** user logs in
- **THEN** library SHALL log INFO with masked credentials (e.g., `username=alice, password=***`)

#### Scenario: Transfer logging

- **WHEN** a transfer is executed
- **THEN** library SHALL log INFO with all relevant fields EXCEPT full OTP or sensitive data

#### Scenario: Job execution logging

- **WHEN** a scheduler job fires
- **THEN** library SHALL log INFO with job_id, job_name, status, duration

---

## Design Notes

This spec follows [OpenSpec format](https://github.com/Fission-AI/OpenSpec). The capabilities listed above are the MUST-HAVE for v0.1.0+. Additional capabilities (e.g., Google Sheets integration, PDF export, advanced analytics) MAY be added in later versions.

### Out of Scope (v0.1)

- Mobile app push notifications
- Voice/TTS notifications (existing in current `apps/function_server/tts.py` can be added later)
- QR code generation (existing in `apps/transfer/qr.py` can be added later)
- Captcha solving (PGBank does not have captcha; explicitly excluded)

### Compatibility

- **Python**: 3.9, 3.10, 3.11, 3.12
- **OS**: Windows, macOS, Linux
- **Dependencies**: requests, cryptography, click, pyyaml, jinja2 (see pyproject.toml)
