# PGBank Unofficial Library — Phase 2-6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 5 missing feature modules required by `openspec/specs/pgbank-unofficial/spec.md`: `history.py`, `scheduler.py`, `webhook.py`, `poller.py`, `cli.py`. Each module is built TDD-style with full test coverage, type hints, documentation, and updates to the public API + README + walkthrough.

**Architecture:** Each module is a self-contained subsystem with:
- Pure Python (no PGBank HTTP coupling where possible)
- Typed dataclasses / Pydantic-style inputs where applicable
- Pluggable interfaces (events, triggers, storage)
- Sync + async APIs (where applicable)
- Backward compatibility — never break existing public API

**Tech Stack:**
- Python 3.9+ (target 3.9, 3.10, 3.11, 3.12 per pyproject.toml)
- `croniter` for cron expression parsing (Phase 3)
- `openpyxl` for Excel export (Phase 2)
- `click` for CLI (Phase 6) — already declared in pyproject optional deps
- `pytest` + `pytest-asyncio` for testing
- `mypy` (relaxed), `ruff`, `black` for quality

---

## Global Constraints

These apply to every task. Read once.

- **Public API exports**: All new classes MUST be added to `src/pgbank_unofficial/__init__.py` AND to `__all__` list
- **Backward compatibility**: NEVER change the signature of existing public methods (`PGBankClient.__init__`, `login`, etc.)
- **Decimal for money**: All monetary values MUST use `decimal.Decimal`, NEVER `float`
- **Type hints**: Every public method MUST have full type hints
- **Tests required**: Each public method needs at least 3 test cases (happy path + 2 edge cases). Aim for 80%+ coverage per module.
- **Docstrings**: Every public class/function MUST have a Google-style docstring with `Args:`, `Returns:`, `Raises:`, `Example:` sections where applicable
- **Documentation**: Update `docs/dev-diary/development-diary.md` with each phase's highlights; update `walkthrough.md` artifact at end
- **Lint compliance**: `ruff check src/pgbank_unofficial/<module>.py` and `black --check src/pgbank_unofficial/<module>.py` MUST pass before commit
- **Async parity**: Where a sync API is added, an async equivalent MUST exist with the same interface (unless the operation is purely synchronous, like cron parsing)
- **No new runtime dependencies without justification**: Only add deps from pyproject.toml's optional extras if absolutely required

---

## Phase Map

| Phase | Module | Spec Section | Priority |
|-------|--------|--------------|----------|
| 2 | `history.py` | Transaction History | P0 (quickest win) |
| 3 | `scheduler.py` | Auto-Payment Scheduling (FLAGSHIP) | P1 |
| 4 | `webhook.py` | Webhook Dispatcher | P2 |
| 5 | `poller.py` | Real-Time Monitoring | P3 |
| 6 | `cli.py` | CLI Tool | P4 |

Each phase follows TDD: failing test → implementation → passing test → commit → review.

---

## Phase 2: Transaction History Module (`history.py`)

**Goal:** Wrap existing `client.get_transaction_history()` with high-level query, search, categorize, and export functionality.

**Files:**
- Create: `src/pgbank_unofficial/history.py` (new module, ~300 lines)
- Create: `tests/test_history.py` (new test file, ~25 test cases)
- Modify: `src/pgbank_unofficial/__init__.py` (add exports)

**Public API:**
```python
@dataclass
class HistoryQuery:
    account_id: Optional[str] = None       # None = all accounts (multi-account mode)
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    direction: Optional[TransactionDirection] = None
    counterparty: Optional[str] = None     # Fuzzy match
    category: Optional[str] = None
    description_search: Optional[str] = None

@dataclass
class CategorizedTransaction(Transaction):
    category: str = "Uncategorized"

class TransactionHistory:
    def __init__(self, client: PGBankClient): ...
    def query(self, q: HistoryQuery) -> list[Transaction]: ...
    def search(self, text: str, *, account_id: Optional[str] = None) -> list[Transaction]: ...
    def categorize(self, transactions: list[Transaction], rules: dict[str, str]) -> list[CategorizedTransaction]: ...
    def query_all_accounts(self, q: HistoryQuery, manager: PGBankManager) -> dict[str, list[Transaction]]: ...

def export_to_excel(transactions, output_path: str | Path, *, account_label: Optional[str] = None) -> None: ...
def export_to_csv(transactions, output_path: str | Path) -> None: ...
def export_to_json(transactions, output_path: str | Path) -> None: ...
```

**Tasks:**

### Task 2.1: HistoryQuery dataclass + TransactionHistory.query()

- [ ] **Step 1**: Write failing test for HistoryQuery validation (min_amount <= max_amount)
- [ ] **Step 2**: Implement `HistoryQuery` dataclass with `__post_init__` validation
- [ ] **Step 3**: Write failing test for `TransactionHistory.query()` (mock client)
- [ ] **Step 4**: Implement `TransactionHistory.query()` (delegates to client.get_transaction_history, applies filters in-memory)
- [ ] **Step 5**: Verify tests pass
- [ ] **Step 6**: Commit

### Task 2.2: TransactionHistory.search() with fuzzy matching

- [ ] **Step 1**: Write failing test for case-insensitive substring match across description, counterparty_name, counterparty_account
- [ ] **Step 2**: Implement `search()` method using simple `in` operator (no external lib)
- [ ] **Step 3**: Test multi-account search (with account_id filter)
- [ ] **Step 4**: Commit

### Task 2.3: TransactionHistory.categorize() with rules

- [ ] **Step 1**: Write failing test for rule-based categorization ("GRAB" → "Di chuyển")
- [ ] **Step 2**: Implement `categorize()` returning `CategorizedTransaction` list
- [ ] **Step 3**: Test case-insensitive rule matching
- [ ] **Step 4**: Test default category "Uncategorized"
- [ ] **Step 5**: Commit

### Task 2.4: Export functions (Excel/CSV/JSON)

- [ ] **Step 1**: Add `openpyxl` to pyproject.toml optional deps (`pip install openpyxl` for users)
- [ ] **Step 2**: Write failing test for `export_to_csv` (uses stdlib `csv`)
- [ ] **Step 3**: Implement `export_to_csv` and `export_to_json`
- [ ] **Step 4**: Write failing test for `export_to_excel` (skip if openpyxl not available, gracefully degrade)
- [ ] **Step 5**: Implement `export_to_excel`
- [ ] **Step 6**: Commit

### Task 2.5: Public API + docs

- [ ] **Step 1**: Add exports to `src/pgbank_unofficial/__init__.py` and `__all__`
- [ ] **Step 2**: Update `README.md` with usage example
- [ ] **Step 3**: Update `walkthrough.md` artifact with Phase 2 completion
- [ ] **Step 4**: Commit + run full test suite

---

## Phase 3: Auto-Payment Scheduler (`scheduler.py`)

**Goal:** Cron/interval/conditional trigger scheduler that executes user-defined actions (transfer, custom callback) on a schedule.

**Files:**
- Create: `src/pgbank_unofficial/scheduler.py` (~600 lines)
- Create: `tests/test_scheduler.py` (~40 test cases)
- Modify: `pyproject.toml` (add `croniter>=2.0` to dependencies)
- Modify: `src/pgbank_unofficial/__init__.py`

**Public API:**
```python
from croniter import croniter

class Trigger(ABC):
    def next_run_at(self, after: datetime) -> datetime: ...

class CronTrigger(Trigger):
    def __init__(self, expression: str, jitter_seconds: int = 0): ...

class IntervalTrigger(Trigger):
    def __init__(self, seconds: int = 0, minutes: int = 0, hours: int = 0, days: int = 0, jitter_seconds: int = 0): ...

class ConditionalTrigger(Trigger):
    def __init__(self, check_every: timedelta, condition: Callable[[PGBankClient], bool]): ...

@dataclass
class Job:
    id: str
    name: str
    trigger: Trigger
    action: Callable[[JobContext], Any]
    account_id: str          # Which account to use
    dry_run: bool = False
    daily_limit: Optional[Decimal] = None
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None

@dataclass
class JobRun:
    job_id: str
    started_at: datetime
    finished_at: Optional[datetime]
    success: bool
    error: Optional[str]
    dry_run: bool

class JobContext:
    def __init__(self, client: PGBankClient, job: Job): ...

class AutoPaymentScheduler:
    def __init__(self, manager: PGBankManager, *, max_workers: int = 2): ...
    def add_job(self, job: Job) -> str: ...
    def remove_job(self, job_id: str) -> None: ...
    def pause_job(self, job_id: str) -> None: ...
    def resume_job(self, job_id: str) -> None: ...
    def run_job_now(self, job_id: str) -> JobRun: ...
    def list_jobs(self) -> list[Job]: ...
    def start(self) -> None: ...        # background thread
    def stop(self) -> None: ...
    def get_history(self, job_id: str) -> list[JobRun]: ...
```

**Tasks:**

### Task 3.1: Trigger hierarchy (Cron, Interval, Conditional)

- [ ] **Step 1**: Write failing test for `CronTrigger.next_run_at("0 9 5 * *")`
- [ ] **Step 2**: Implement using `croniter`
- [ ] **Step 3**: Write failing test for `IntervalTrigger` with various combinations
- [ ] **Step 4**: Implement `IntervalTrigger`
- [ ] **Step 5**: Write failing test for `ConditionalTrigger`
- [ ] **Step 6**: Implement `ConditionalTrigger`
- [ ] **Step 7**: Commit

### Task 3.2: Job dataclass + JobContext

- [ ] **Step 1**: Write failing test for `Job` validation
- [ ] **Step 2**: Implement `Job` dataclass
- [ ] **Step 3**: Implement `JobContext` with client + job reference
- [ ] **Step 4**: Commit

### Task 3.3: AutoPaymentScheduler core (add/remove/pause/resume/list)

- [ ] **Step 1**: Write failing test for `add_job` returns unique ID
- [ ] **Step 2**: Implement in-memory job registry
- [ ] **Step 3**: Write tests for `pause_job`, `resume_job`, `remove_job`
- [ ] **Step 4**: Implement state management
- [ ] **Step 5**: Commit

### Task 3.4: Job execution engine + run_job_now

- [ ] **Step 1**: Write failing test for `run_job_now` with action returning result
- [ ] **Step 2**: Implement execution engine (calls action(job_context))
- [ ] **Step 3**: Write tests for daily_limit enforcement
- [ ] **Step 4**: Write tests for dry_run mode
- [ ] **Step 5**: Write tests for failure handling (record JobRun with error)
- [ ] **Step 6**: Commit

### Task 3.5: Background loop (start/stop)

- [ ] **Step 1**: Write failing test for `start()` triggering due jobs
- [ ] **Step 2**: Implement polling loop in background thread
- [ ] **Step 3**: Test `stop()` cleanly shuts down
- [ ] **Step 4**: Test concurrent job execution (max_workers)
- [ ] **Step 5**: Commit

### Task 3.6: Job history (in-memory + optional persistence)

- [ ] **Step 1**: Write failing test for `get_history` returning JobRun list
- [ ] **Step 2**: Implement history buffer (deque with maxlen)
- [ ] **Step 3**: Commit

### Task 3.7: Public API + docs

- [ ] **Step 1**: Add exports to `__init__.py` and `__all__`
- [ ] **Step 2**: Update `README.md` with `pgbank-unofficial/scheduler` example (existing code already references it)
- [ ] **Step 3**: Update `walkthrough.md` artifact
- [ ] **Step 4**: Commit + run full test suite

---

## Phase 4: Webhook Dispatcher (`webhook.py`)

**Goal:** Event dispatcher that sends events to Discord, Telegram, custom HTTP endpoints with HMAC signing and exponential-backoff retry.

**Files:**
- Create: `src/pgbank_unofficial/webhook.py` (~400 lines)
- Create: `tests/test_webhook.py` (~30 test cases)
- Modify: `src/pgbank_unofficial/__init__.py`

**Public API:**
```python
@dataclass
class Event:
    type: str
    timestamp: datetime
    data: dict

class BalanceEvent(Event): ...
class TransactionEvent(Event): ...
class JobEvent(Event): ...

class WebhookDispatcher:
    def __init__(self, *, max_retries: int = 5): ...
    def subscribe(self, event_type: type, callback: Callable[[Event], Awaitable[None]]) -> None: ...
    def register_discord(self, webhook_url: str, *, events: list[type]) -> None: ...
    def register_telegram(self, bot_token: str, chat_id: str, *, events: list[type], template: str = "...") -> None: ...
    def register_webhook(self, url: str, *, secret: Optional[str] = None, events: list[type], headers: dict = None) -> None: ...
    async def dispatch(self, event: Event) -> None: ...
```

**Tasks:**

### Task 4.1: Event hierarchy (Event, BalanceEvent, TransactionEvent, JobEvent)

- [ ] **Step 1**: Write failing test for Event dataclass
- [ ] **Step 2**: Implement Event + subclasses
- [ ] **Step 3**: Commit

### Task 4.2: HMAC signing + HTTP delivery

- [ ] **Step 1**: Write failing test for HMAC-SHA256 signing
- [ ] **Step 2**: Implement signature helper
- [ ] **Step 3**: Write failing test for HTTP POST delivery (using `respx` mock)
- [ ] **Step 4**: Implement async delivery with httpx
- [ ] **Step 5**: Commit

### Task 4.3: Retry with exponential backoff

- [ ] **Step 1**: Write failing test for retry on 5xx (1st attempt fails, 2nd succeeds)
- [ ] **Step 2**: Implement retry logic with `asyncio.sleep` and backoff (2s, 4s, 8s...)
- [ ] **Step 3**: Test max_retries exhaustion
- [ ] **Step 4**: Commit

### Task 4.4: Discord + Telegram formatters

- [ ] **Step 1**: Write failing test for Discord embed payload generation
- [ ] **Step 2**: Implement Discord formatter
- [ ] **Step 3**: Write failing test for Telegram template (Jinja2)
- [ ] **Step 4**: Implement Telegram formatter
- [ ] **Step 5**: Commit

### Task 4.5: Subscription (in-process callbacks)

- [ ] **Step 1**: Write failing test for `subscribe` + `dispatch` calling callback
- [ ] **Step 2**: Implement in-process subscriber registry
- [ ] **Step 3**: Commit

### Task 4.6: Public API + docs

- [ ] **Step 1**: Add exports to `__init__.py` and `__all__`
- [ ] **Step 2**: Update `README.md`
- [ ] **Step 3**: Update `walkthrough.md`
- [ ] **Step 4**: Commit + run full test suite

---

## Phase 5: Real-Time Monitoring (`poller.py`)

**Goal:** Background poller that detects balance changes and new transactions, dispatches events.

**Files:**
- Create: `src/pgbank_unofficial/poller.py` (~300 lines)
- Create: `tests/test_poller.py` (~20 test cases)
- Modify: `src/pgbank_unofficial/__init__.py`

**Public API:**
```python
class BalancePoller:
    def __init__(self, client: PGBankClient, dispatcher: WebhookDispatcher, *, interval: timedelta = timedelta(minutes=5), threshold_vnd: Decimal = Decimal("1000")): ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def alert_below(self, amount: Decimal) -> None: ...

class TransactionMonitor:
    def __init__(self, client: PGBankClient, dispatcher: WebhookDispatcher, *, interval: timedelta = timedelta(minutes=2)): ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

**Tasks:**

### Task 5.1: BalancePoller

- [ ] **Step 1**: Write failing test for `start()` polling balance every N seconds
- [ ] **Step 2**: Implement polling loop
- [ ] **Step 3**: Write test for `BalanceEvent` dispatch when balance changes > threshold
- [ ] **Step 4**: Commit

### Task 5.2: TransactionMonitor

- [ ] **Step 1**: Write failing test for fetching new transactions since last poll
- [ ] **Step 2**: Implement monitor with timestamp tracking
- [ ] **Step 3**: Write test for `TransactionEvent` dispatch
- [ ] **Step 4**: Commit

### Task 5.3: Threshold alert (`alert_below`)

- [ ] **Step 1**: Write failing test for `alert_below` triggering custom event
- [ ] **Step 2**: Implement threshold logic
- [ ] **Step 3**: Commit

### Task 5.4: Public API + docs

- [ ] **Step 1**: Add exports to `__init__.py` and `__all__`
- [ ] **Step 2**: Update `README.md`
- [ ] **Step 3**: Update `walkthrough.md`
- [ ] **Step 4**: Commit + run full test suite

---

## Phase 6: CLI Tool (`cli.py`)

**Goal:** Command-line interface `pgbank` for non-coders using Click.

**Files:**
- Create: `src/pgbank_unofficial/cli.py` (~300 lines)
- Create: `tests/test_cli.py` (~15 test cases using `click.testing.CliRunner`)
- Modify: `pyproject.toml` (add `console_scripts` entry point)
- Modify: `src/pgbank_unofficial/__init__.py`

**CLI Structure:**
```
pgbank
├── account
│   ├── add        # --username --password --browser-id [--proxy] [--nickname]
│   ├── list       # [--json]
│   └── remove     # --nickname
├── balance        # [--account] [--json]
├── schedule
│   ├── add        # --name --cron --account --to --amount
│   ├── list       # [--json]
│   └── remove     # --id
└── history        # --from-date --to-date [--account] [--json]
```

**Tasks:**

### Task 6.1: Click group + `account add/list/remove`

- [ ] **Step 1**: Write failing test for `pgbank account add --help`
- [ ] **Step 2**: Implement Click group
- [ ] **Step 3**: Implement `account add` command (writes to file)
- [ ] **Step 4**: Implement `account list` with `--json` flag
- [ ] **Step 5**: Implement `account remove`
- [ ] **Step 6**: Commit

### Task 6.2: `balance` command

- [ ] **Step 1**: Write failing test for `pgbank balance` (output table)
- [ ] **Step 2**: Implement using PrettyTable or tabulate
- [ ] **Step 3**: Test `--json` output
- [ ] **Step 4**: Commit

### Task 6.3: `schedule add/list/remove`

- [ ] **Step 1**: Write failing test for `pgbank schedule add`
- [ ] **Step 2**: Implement schedule commands
- [ ] **Step 3**: Commit

### Task 6.4: `history` command

- [ ] **Step 1**: Write failing test for `pgbank history --from-date 2024-01-01`
- [ ] **Step 2**: Implement history command using `pgbank_unofficial.history`
- [ ] **Step 3**: Commit

### Task 6.5: Entry point + docs

- [ ] **Step 1**: Add `[project.scripts]` entry in `pyproject.toml`
- [ ] **Step 2**: Update `README.md` with CLI usage section
- [ ] **Step 3]: Update `walkthrough.md`
- [ ] **Step 4**: Commit + run full test suite

---

## Verification Plan

After each phase:

1. **Run all tests**: `pytest tests/ -v`
2. **Lint check**: `ruff check src/pgbank_unofficial/`
3. **Format check**: `black --check src/pgbank_unofficial/`
4. **Mypy check**: `mypy src/pgbank_unofficial/<module>.py`
5. **Coverage**: `pytest --cov=pgbank_unofficial.<module> tests/test_<module>.py`

After all 5 phases:

1. **Final whole-branch review** (using superpowers:requesting-code-review)
2. **Update walkthrough.md** with completion summary
3. **Tag release** v0.3.0 in git

---

## Notes

- Each phase builds on prior phases but is **independently testable** (you can ship history.py without scheduler if needed).
- Subagents should reference `openspec/specs/pgbank-unofficial/spec.md` for the canonical requirements.
- Existing `get_transaction_history()` in `client.py` (line 774) already returns `list[Transaction]` — wrap it, don't reimplement.
- Existing `manager.py` provides `PGBankManager` for multi-account context.
