# PGBank Unofficial API ( tài khoản cá nhân )

> **Unofficial Python library cho PGBank API** — Multi-account, scheduled payments, webhooks, transaction history & nhiều hơn nữa.

## ✨ Tính năng

- **CUSTOM THANH TOÁN TỰ ĐỘNG FREE**, custom order link, QR, theo dõi theo Description làm mã đơn, có thể tự implement các phương pháp khác nhau.
- 🔔 **Webhook dispatcher** — Zalo, Telegram, Google Sheet custom HTTP, có thể cấu hình để nhận thông báo chuyển tiền, nhận tiền về hệ thống khác.
- 🔐 **Authentication** với OTP flow + session persistence
- 👥 **Multi-account management** với proxy/BrowserID linh hoạt per-account
- ⏰ **Auto-payment scheduler** — lập lịch chuyển khoản định kỳ, cron, conditional
- 📊 **Transaction history** với query nâng cao, categorization, export Excel/CSV/JSON
- 📈 **Real-time monitoring** — balance threshold alerts, transaction detection
- 🔄 **Sync + Async API** song song
- 💻 **CLI tool** (`pgbank` command)
- 🗄️ **Storage abstraction** — SQLite default, swap sang Redis/Postgres

## 📦 Cài đặt

```bash
# ( chưa đẩy lên thư viện), tạm thời clone về.
pip install pgbank-unofficial
```

## 🚀 Quickstart

```python
from pgbank_unofficial import PGBankManager, Account
from decimal import Decimal

# Setup multi-account manager
mgr = PGBankManager()

# Add accounts (proxy optional, browser_id required)
mgr.add_account(Account(
    username="alice",
    password="your_password",
    browser_id="your_browser_id",                # Required
    proxy="http://proxy1:8080",                  # Optional
    nickname="alice-personal",
))

mgr.add_account(Account(
    username="bob",
    password="bob_password",
    browser_id="shared_browser_id",              # Có thể share browser_id
    proxy="http://proxy2:8080",                  # Proxy khác nhau
    nickname="bob-personal",
))

# Health check all accounts
status = mgr.health_check()
print(status)
# {'alice-personal': <AccountStatus.ALIVE>, 'bob-personal': <AccountStatus.ALIVE>}

# Get all balances
balances = mgr.get_all_balances()
for account_id, balance in balances.items():
    print(f"{account_id}: {balance.available:,.0f} VND")
```

## 💾 Session Storage (Pluggable Backends)

By default, sessions are stored in a JSON file. If you want to persist sessions to a different backend (SQLite, Supabase, Redis, in-memory, or anything else), implement the `BaseSessionStorage` interface:

```python
from pgbank_unofficial import PGBankClient, BaseSessionStorage, MemorySessionStorage

# ── Built-in backends ───────────────────────────────────────────

# 1. Default: a single JSON file (legacy `session_path=` style)
client = PGBankClient(
    username="alice", password="...", browser_id="...",
    session_path="./session.json",
)

# 2. One file per username in a directory (great for multi-account setups)
from pgbank_unofficial import DirSessionStorage
client = PGBankClient(
    username="alice", password="...", browser_id="...",
    session_storage=DirSessionStorage("./sessions"),
)

# 3. In-memory (tests, ephemeral environments)
client = PGBankClient(
    username="alice", password="...", browser_id="...",
    session_storage=MemorySessionStorage(),
)

# ── Custom backend: SQLite ──────────────────────────────────────
import sqlite3, json

class SQLiteSessionStorage(BaseSessionStorage):
    def __init__(self, db_path: str = "sessions.sqlite3"):
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "create table if not exists sessions "
            "(username text primary key, data text not null, updated_at text not null)"
        )

    def save_session(self, username, data):
        self._conn.execute(
            "insert or replace into sessions(username, data, updated_at) "
            "values (?, ?, datetime('now'))",
            (username, json.dumps(data)),
        )
        self._conn.commit()

    def load_session(self, username):
        row = self._conn.execute(
            "select data from sessions where username=?", (username,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def delete_session(self, username):
        self._conn.execute("delete from sessions where username=?", (username,))
        self._conn.commit()

client = PGBankClient(
    username="alice", password="...", browser_id="...",
    session_storage=SQLiteSessionStorage("pgbank.sqlite3"),
)

# ── Custom backend: Supabase / PostgreSQL ───────────────────────
# Same pattern: subclass BaseSessionStorage and implement
#   save_session(username, data)  -> write the data
#   load_session(username)        -> return dict or None
#   delete_session(username)      -> remove the record
```

The same `session_storage` parameter works on `AsyncPGBankClient` as well.

## ⏰ Auto-Payment Example

```python
from pgbank_unofficial.scheduler import AutoPaymentScheduler, Job, CronTrigger
from decimal import Decimal

scheduler = AutoPaymentScheduler(mgr)

# Hàng tháng chuyển 500k cho mẹ vào ngày 5 lúc 9h sáng
scheduler.add_job(Job(
    name="Mẹ - tiền điện hàng tháng",
    trigger=CronTrigger("0 9 5 * *"),
    action=lambda ctx: ctx.client("alice-personal").transfer(
        from_account="alice_main",
        to_account="MOM_ACCOUNT",
        amount=Decimal("500000"),
        message="Tien dien thang {month}",
    ),
))

scheduler.start()  # Chạy background
```

## 📊 Transaction History

```python
from pgbank_unofficial.history import HistoryQuery, export_to_excel
from datetime import date

history = mgr.history()

# Query
txns = history.query(HistoryQuery(
    from_date=date(2026, 6, 1),
    to_date=date(2026, 6, 23),
    min_amount=Decimal("1000000"),
))

# Export Excel
export_to_excel(txns, output_path="transactions_June.xlsx")
```

## 💻 CLI

```bash
pgbank account add --username alice --password xxx --browser-id bid_xxx
pgbank balance
pgbank history --from 2026-06-01 --to 2026-06-23 --export xlsx
pgbank schedule add --name "..." --cron "0 9 5 * *" --account alice --to MOM_ACC --amount 500000
```

## 📖 Documentation

- [Getting Started](docs/getting-started.md) (coming soon)
- [OpenSpec specs](openspec/specs/pgbank-unofficial/spec.md)
- [API Reference](docs/api-reference.md) (coming soon)

## ⚠️ Disclaimer

Đây là project **KHÔNG CHÍNH THỨC**, không liên kết với PGBank. Sử dụng có thể vi phạm điều khoản của ngân hàng và dẫn đến khóa tài khoản. Bạn tự chịu trách nhiệm.

## 📄 License

MIT License — see [LICENSE](LICENSE).

## Minhdevtry
