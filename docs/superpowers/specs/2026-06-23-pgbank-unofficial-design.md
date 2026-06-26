# Design — PGBank Unofficial Library

**Date:** 2026-06-23
**Status:** ✅ Approved by user
**Owner:** the2ricebowls (LeVietHung)
**Repo:** https://github.com/netrotion/pgbank-unofficial *(tạo khi ready)*
**PyPI:** `pgbank-unofficial`

---

## Background

Hiện tại có project tham khảo [VCB-API](https://github.com/netrotion/VCB-API) (cũng do LeVietHung phát triển) — tuy nhiên VCB-API chỉ có ~4 method cơ bản, captcha solver và 1 tool lấy BrowserID.

Dự án PGBank hiện tại ở [pg/pgbank/](../pg/pgbank/) đã có nhiều hơn thế nhiều (56+ API method, full OTP flow, 4 loại transfer, Admin Dashboard, Function Server, Transfer UI, glassmorphism design), nhưng vẫn là **monolithic application** chưa tách thành library.

Mục tiêu của design này: **Tách lõi PGBank thành một thư viện Python standalone** để:
1. Nhiều người ở nhiều nơi có thể `pip install pgbank-unofficial`
2. Project PGBank hiện tại sẽ **refactor** lại để dùng thư viện làm core (Phase 5)
3. Đảm bảo chất lượng "sịn hơn, nhiều tính năng hơn" VCB-API

---

## Goals (MUST-HAVE)

1. **PyPI package** `pgbank-unofficial` installable qua pip
2. **Multi-account management** với proxy/BrowserID linh hoạt per-account (bắt buộc BrowserID, proxy optional)
3. **Auto-payment scheduler** (flagship) — scheduled/recurring/conditional transfers, có safety (jitter, daily limit, dry-run)
4. **Webhook dispatcher** — Discord, Telegram, custom HTTP
5. **Transaction history** — query/search/categorize/export (CSV/Excel/JSON)
6. **Sync + Async API** song song
7. **CLI tool** (`pgbank` command) cho non-coders
8. **OpenSpec specs** để các agent khác hiểu được dự án

## Non-Goals (OUT of Scope for v0.1)

- Mobile push notifications
- Voice/TTS (existing trong `apps/function_server/tts.py` có thể thêm sau)
- QR code generation (existing trong `apps/transfer/qr.py` có thể thêm sau)
- **Captcha solving** (PGBank không có captcha — đã loại trừ rõ ràng)

---

## Considered Approaches

### Approach A: Layered Architecture + Multi-Account Manager ✅ CHOSEN

```
pgbank_unofficial/
├── client.py            # Low-level HTTP (1 client = 1 session)
├── manager.py           # Multi-account orchestrator
├── models.py            # Typed dataclasses
├── scheduler/           # Auto-payment
├── webhooks/            # Event dispatcher
├── history/             # Query/export
├── monitoring/          # Polling + alerts
├── integrations/        # Telegram/Discord/Sheets
├── cli/                 # pgbank command
└── storage/             # SQLite default
```

**Pros:**
- Single Responsibility, mỗi layer 1 việc
- Multi-account tự nhiên (manager quản lý N clients)
- OpenSpec dễ viết (1 capability = 1 module)
- Dễ test từng layer độc lập
- Performance: per-account connection pool

**Cons:**
- Nhiều files → cần documentation kỹ
- User phải hiểu manager vs client

### Approach B: Single Client với Multi-Account Context ❌

```python
client = PGBankClient()
client.add_account("alice", ...)
await client.get_balance(account="alice")
```

**Pros:** 1 class, ít boilerplate
**Cons:** Concurrent ops phức tạp, khó tách bạch state/session, không scale

### Approach C: Event-driven Plugin Architecture ❌

Tất cả operation phát event → plugin subscribe.

**Pros:** Cực extensible
**Cons:** Quá abstract cho v0.1, learning curve cao, user phải hiểu event bus

---

## Architecture

### Layer Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  USER CODE                                                        │
│  (Script / CLI / Web App / Telegram Bot / Google Sheets)         │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
        ═════════════════════════╪══════════════════════════
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│  PGBankManager (multi-account orchestrator)                       │
│   • Accounts registry (SQLite-backed)                            │
│   • Per-account: credentials + proxy + browser_id                │
│   • Lazy session creation                                        │
│   • Rate limiting & global semaphore                            │
└────────────────┬─────────────────────────────────────────────────┘
                 │
       ┌─────────┴──────────┐
       ▼                    ▼
┌──────────────┐    ┌──────────────┐
│  Sync API    │    │  Async API   │   ◄── Public surface
│  (scripts)   │    │  (FastAPI)   │
└──────┬───────┘    └──────┬───────┘
       │                   │
┌──────┴───────────────────┴──────────┐
│  PGBankClient (1 account = 1 client) │
│   • Low-level HTTP w/ encryption    │
│   • Session persistence              │
│   • Retry & circuit breaker          │
└──────────────────────────────────────┘
                 │
┌────────────────┴────────────────────────────────────────┐
│  Cross-cutting features                                │
│  ┌────────────────┐ ┌──────────────┐ ┌──────────────┐ │
│  │ Auto-Payment   │ │ Webhook      │ │ Storage      │ │
│  │ Scheduler      │ │ Dispatcher   │ │ (SQLite)     │ │
│  └────────────────┘ └──────────────┘ └──────────────┘ │
└───────────────────────────────────────────────────────┘
                 │
┌────────────────┴────────────────────────────────────────┐
│  Optional Integrations                                  │
│  • Telegram bot  • Discord  • Google Sheets            │
│  • CSV/Excel export  • (NO captcha — PGBank không có)  │
└───────────────────────────────────────────────────────┘
```

### Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| `client.py` | 1 HTTP client = 1 PGBank session, low-level encryption |
| `manager.py` | Multi-account registry, lazy client creation |
| `models.py` | Dataclasses: Account, Balance, Transaction, TransferResult |
| `auth/` | BrowserID + proxy management, session persistence |
| `http/` | Transport (TLS bypass), encryption, retry/circuit-breaker |
| `scheduler/` | Triggers (Cron/Interval/Conditional), Job lifecycle, safety |
| `webhooks/` | Event types, dispatcher, Discord/Telegram/HTTP delivery |
| `history/` | Query, search, categorize, export (CSV/Excel/JSON) |
| `monitoring/` | BalancePoller, TransactionMonitor |
| `storage/` | SQLite backend, schema migrations |
| `integrations/` | Telegram bot, Discord webhook, Google Sheets sync |
| `cli/` | `pgbank` command via Click/Typer |

---

## Key Design Decisions

### 1. Dataclasses everywhere (no raw dicts)

User-facing API returns typed dataclasses (`Balance`, `Transaction`, `TransferResult`). JSON serialization qua `to_dict()`. Đảm bảo IDE autocomplete và type checking.

### 2. Decimal for money

Tất cả monetary values dùng `decimal.Decimal`. **Không bao giờ dùng float** cho tiền.

### 3. BrowserID là mandatory

`Account` không có `browser_id` → raise `MissingBrowserIDError` immediately. Proxy optional.

### 4. Sync + Async song song

Mọi public API có cả sync và async version. Dùng `asyncio` cho async, `concurrent.futures.ThreadPoolExecutor` cho sync parallel ops.

### 5. SQLite default, swappable

Default storage ở `~/.pgbank_unofficial/data.db`. Interface `Storage` cho phép swap sang Redis/Postgres sau.

### 6. Auto-payment safety first

- **Jitter** (default 30s) tránh pattern detection
- **Daily limit** per account (default 50M VND) chống bug làm bay tiền
- **Dry-run** mode test job mà không chuyển thật
- **Auto-pause** sau 3 lần fail liên tiếp
- **OTP callback** để user cấp OTP khi cần

### 7. OpenSpec for cross-agent compatibility

Spec viết theo format [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec) — định dạng chuẩn để AI agents (Claude, Gemini, GPT) có thể parse và hiểu requirements.

### 8. NO captcha

PGBank không có captcha → không tốn effort. Hook `on_captcha_needed` có thể thêm sau nếu cần (future-proof).

---

## Success Criteria

### v0.1.0 (Phase 1 complete)
- [ ] `pip install pgbank-unofficial` thành công
- [ ] `from pgbank_unofficial import PGBankClient, PGBankManager` import được
- [ ] Login + get_balance hoạt động với test credentials
- [ ] Unit test coverage > 90%
- [ ] CI/CD xanh trên 3 Python versions

### v0.5.0 (Phase 3 complete)
- [ ] Multi-account manager với proxy/browser_id per account
- [ ] Auto-payment scheduler production-ready
- [ ] Webhook dispatcher (Discord + Telegram + HTTP) hoạt động
- [ ] Documentation đầy đủ (mkdocs)

### v1.0.0 (Phase 6 complete)
- [ ] Full feature parity + CLI tool
- [ ] Project PGBank (`pg/pgbank/`) refactor xong, dùng library
- [ ] Public release trên PyPI với stable API
- [ ] 5+ GitHub stars, 100+ PyPI downloads

---

## Verification Plan

### Automated

```bash
# Unit tests (fast, no network)
pytest tests/unit/ -v

# Integration tests (requires test credentials)
export PGBANK_TEST_USERNAME=alice
export PGBANK_TEST_PASSWORD=xxx
export PGBANK_TEST_BROWSER_ID=bid_xxx
pytest tests/integration/ -v

# Coverage
pytest --cov=pgbank_unofficial --cov-report=term-missing

# Type check
mypy src/pgbank_unofficial/ --strict

# Lint
ruff check src/
black --check src/

# Build + publish check
python -m build
twine check dist/*
```

### Manual

1. **CLI smoke test**: `pgbank --help`, `pgbank account add`, `pgbank balance`
2. **End-to-end transfer**: Dùng test account, chuyển 1000đ, verify trong history
3. **Scheduler test**: Tạo job mỗi phút, check history
4. **Webhook test**: Discord webhook nhận được event
5. **Multi-account test**: 2 accounts với proxy/browser_id khác nhau
6. **PyPI Test publish**: Install từ TestPyPI, verify import OK

---

## Open Questions (Resolved)

| Question | Resolution |
|----------|------------|
| Package vs sub-package? | **Package** trên PyPI — dễ cài, dễ dùng ở mọi nơi |
| Captcha có cần? | **Không** — PGBank không có captcha |
| Tính năng gì thêm? | Multi-account, scheduled payment, webhook, history rich query, CLI |
| Sync hay Async trước? | **Cả hai** song song từ đầu |
| Spec format? | **OpenSpec** format (Fission-AI) |
| BrowserID shared hay unique? | **Cả hai hỗ trợ** — user tự quyết định per-account |

---

## Related Documents

- [OpenSpec spec.md](../../openspec/specs/pgbank-unofficial/spec.md) — Formal requirements (20+ scenarios)
- [PGBank project hiện tại](../pg/pgbank/) — Code nguồn sẽ refactor trong Phase 5
- [VCB-API reference](https://github.com/netrotion/VCB-API) — Đối chiếu để đảm bảo "tốt hơn"

---

## Next Steps

Theo brainstorming skill workflow, bước tiếp theo là:

1. ✅ **Brainstorm completed** (file này)
2. ✅ **Spec written** (`openspec/specs/pgbank-unofficial/spec.md`)
3. ⏳ **User review spec** (gate — bạn đọc và duyệt)
4. → **Invoke writing-plans skill** để tạo implementation plan chi tiết
