"""PGBank API constants — SERVICE URLs, MID codes, bank codes.

Sourced from reverse-engineering the PGBank IB web bundle.
These values change rarely but should be verified against the live
``mount.json`` + network captures when adding new endpoints.

Layout:
    MID = numeric codes per endpoint (4-digit)
    SERVICE = URL path segments
    DEFAULT_KEY_MIDS = endpoints that use the mount-config default
                       server pubkey (pre-login / banner / OTP)
"""

from __future__ import annotations

# ── Service URL segments ─────────────────────────────────────────────────────
SERVICE = {
    "AUTH": "auth-service",
    "UTILITY": "utility-service",
    "BANK": "bank-service",
    "NAPAS": "napas-service",
}

# ── Message IDs (4-digit codes identifying each endpoint) ────────────────────
MID = {
    # Auth flow
    "LOGIN": "1004",
    "CONFIRM_OTP": "1002",
    "LOGOUT": "2002",
    "RESET_PASSWORD_BEFORE_LOGIN": "1006",
    "CHANGE_PASSWORD_AFTER_LOGIN": "2001",
    # Utility
    "GET_FEATURES": "8001",
    "BANNER_BACKGROUND": "8003",
    "GET_CUSTOMER_INFO": "8041",
    "GET_CONFIG": "8024",
    "GET_CONTACTS": "8014",
    "CREATE_CONTACT": "8015",
    "UPDATE_CONTACT": "8016",
    "REMOVE_CONTACT": "8017",
    "GET_TEMPLATE": "8018",
    "GET_LIST_BANK": "8022",
    # Bank
    "AVAILABLE_BALANCE": "3008",
    "GET_ACCOUNT_PAYMENTS": "3004",
    "SET_DEFAULT_ACCOUNT": "3005",
    "GET_ACCOUNT_SAVING": "3006",
    "GET_ACCOUNT_SOURCE": "3009",
    "GET_TRANSACTION_HISTORY": "3010",
    "GET_DETAIL_TRANSACTION_HISTORY": "3012",
    "GET_SAVINGS_PRODUCTS": "4050",
    "GET_INTEREST_RATES": "4051",
    "GET_LOAN_LIST": "5030",
    "GET_LOAN_DETAIL": "5031",
    "GET_OVERDRAFT_LIST": "5032",
    "GET_OVERDRAFT_DETAIL": "5033",
    "PCRT": "3007",
    "DECREE13": "2008",
    # Transfers
    "GET_RECEIVER_NAME": "5000",
    "TRANSFER_DOMESTIC": "5001",
    "VERIFY_TRANSFER_DOMESTIC": "5002",
    "CONFIRM_TRANSFER_DOMESTIC": "5003",
    "INIT_TRANSFER_SAMEOWNER": "5004",
    "CONFIRM_TRANSFER_SAMEOWNER": "5005",
    "GET_RECEIVER_NAME_NAPAS": "5009",
    "INIT_TRANSFER_NAPAS": "5010",
    "VERIFY_TRANSFER_NAPAS": "5011",
    "CONFIRM_TRANSFER_NAPAS": "5012",
    "INIT_TRANSFER_CITAD": "5006",
    "VERIFY_TRANSFER_CITAD": "5007",
    "CONFIRM_TRANSFER_CITAD": "5008",
}

# ── MIDs that use the mount-config default server pubkey (no session) ────────
DEFAULT_KEY_MIDS: set[str] = {
    MID["LOGIN"],
    MID["CONFIRM_OTP"],
    MID["RESET_PASSWORD_BEFORE_LOGIN"],
    MID["BANNER_BACKGROUND"],
}


# ── Response codes (PGBank error/success codes) ──────────────────────────────
class Code:
    """Standard response codes from PGBank API."""

    SUCCESS = "00"  # OK (no OTP needed)
    OTP_REQUIRED = "01"  # OTP step required
    INVALID_CREDENTIALS = "101"  # Wrong username/password
    SESSION_EXPIRED = "114"  # Session expired (different from OTP_REQUIRED in some contexts)


# ── Bank codes (NAPAS) ────────────────────────────────────────────────────────
class BankCode:
    """NAPAS bank codes for inter-bank transfers."""

    VIETCOMBANK = "970436"
    BIDV = "970418"
    VIETINBANK = "970415"
    AGRIBANK = "970405"
    MB = "970422"
    TECHCOMBANK = "970407"
    VPBANK = "970432"
    TPBANK = "970423"
    ACB = "970416"
    SACOMBANK = "970403"
    HDBANK = "970437"
    OCB = "970448"
    MSB = "970426"
    SEABANK = "970440"
    SHB = "970443"
    VIB = "970441"
    EXIMBANK = "970431"
    PGBANK = "970430"
    NCBANK = "970419"
    NAM_A = "970428"
    KIENLONG = "970452"
    VIETBANK = "970433"
    BVBANK = "970454"
    ABBANK = "970425"
    LPBANK = "970449"
    CAKE = "546034"
    HSBC = "458761"
    SHINHAN = "970424"
    WOORI = "970457"
    CIMB = "422589"
    UBANK = "546035"
    VIETTEL_MONEY = "971005"
    VNPT_MONEY = "971011"
