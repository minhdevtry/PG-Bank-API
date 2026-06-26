"""PGBank Unofficial Library - typed Python client for PGBank API.

Quickstart:
    >>> from pgbank_unofficial import PGBankClient
    >>> client = PGBankClient(username="alice", password="xxx", browser_id="bid_xxx")
    >>> client.login()  # may require OTP
    >>> balance = client.get_balance()
    >>> print(balance.available)
"""

from pgbank_unofficial.async_client import AsyncPGBankClient
from pgbank_unofficial.cli import app as pgbank
from pgbank_unofficial.client import PGBankClient
from pgbank_unofficial.exceptions import (
    AuthenticationError,
    MissingBrowserIDError,
    PGBankError,
    RateLimitError,
    SessionExpiredError,
    TimeoutError,
    TransferError,
)
from pgbank_unofficial.history import (
    CategorizedTransaction,
    HistoryQuery,
    TransactionHistory,
    export_to_csv,
    export_to_excel,
    export_to_json,
    query_all_accounts,
)
from pgbank_unofficial.manager import PGBankManager
from pgbank_unofficial.models import (
    Account,
    AccountInfo,
    AccountStatus,
    Balance,
    BankAccount,
    Transaction,
    TransactionDirection,
    TransferResult,
)
from pgbank_unofficial.poller import (
    BalanceChangedEvent,
    BalancePoller,
    BalancePollerError,
    BalanceSnapshot,
    TransactionMonitor,
    TransactionPollerError,
)
from pgbank_unofficial.scheduler import (
    AutoPaymentScheduler,
    ConditionalTrigger,
    CronTrigger,
    IntervalTrigger,
    Job,
    JobContext,
    JobRun,
    Trigger,
)
from pgbank_unofficial.storage import (
    BaseAsyncSessionStorage,
    BaseSessionStorage,
    BaseStorage,
    DirSessionStorage,
    FileSessionStorage,
    MemorySessionStorage,
    MemoryStorage,
    SQLiteStorage,
)
from pgbank_unofficial.vietqr import ParsedQR, VietQR, parse_qr
from pgbank_unofficial.webhook import (
    DeliveryRecord,
    Event,
    Subscription,
    WebhookDispatcher,
)

__version__ = "0.2.0"

__all__ = [
    # Version
    "__version__",
    # Core clients
    "PGBankClient",
    "AsyncPGBankClient",
    "PGBankManager",
    # Models
    "Account",
    "AccountInfo",
    "AccountStatus",
    "BankAccount",
    "Balance",
    "Transaction",
    "TransactionDirection",
    "TransferResult",
    # VietQR
    "VietQR",
    "ParsedQR",
    "parse_qr",
    # Storage
    "BaseSessionStorage",
    "BaseAsyncSessionStorage",
    "FileSessionStorage",
    "DirSessionStorage",
    "MemorySessionStorage",
    "BaseStorage",
    "SQLiteStorage",
    "MemoryStorage",
    # History
    "HistoryQuery",
    "CategorizedTransaction",
    "TransactionHistory",
    "query_all_accounts",
    "export_to_csv",
    "export_to_json",
    "export_to_excel",
    # Scheduler
    "Trigger",
    "CronTrigger",
    "IntervalTrigger",
    "ConditionalTrigger",
    "Job",
    "JobContext",
    "JobRun",
    "AutoPaymentScheduler",
    # Poller
    "BalanceSnapshot",
    "BalanceChangedEvent",
    "BalancePoller",
    "BalancePollerError",
    "TransactionMonitor",
    "TransactionPollerError",
    # Webhook
    "Event",
    "Subscription",
    "DeliveryRecord",
    "WebhookDispatcher",
    # CLI
    "pgbank",
    # Exceptions
    "PGBankError",
    "AuthenticationError",
    "SessionExpiredError",
    "MissingBrowserIDError",
    "TimeoutError",
    "RateLimitError",
    "TransferError",
]
