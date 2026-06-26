"""Asynchronous PGBank API client (mirror of :class:`PGBankClient`).

Uses ``httpx.AsyncClient`` for transport. Functionally identical to the sync
client — every method has an async equivalent.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from pgbank_unofficial._algorithm import (
    BASE_URL,
    ORIGIN,
    decrypt_response,
    encrypt_request,
    gen_keys,
    make_x_request_id,
)
from pgbank_unofficial._params import MID, SERVICE
from pgbank_unofficial.client import VN_TZ, PGBankClient
from pgbank_unofficial.exceptions import (
    AuthenticationError,
    MissingBrowserIDError,
    PGBankError,
    SessionExpiredError,
)
from pgbank_unofficial.exceptions import (
    TimeoutError as PGBankTimeoutError,
)
from pgbank_unofficial.models import (
    AccountInfo,
    Balance,
    BankAccount,
    Transaction,
    TransactionDirection,
)
from pgbank_unofficial.storage import BaseSessionStorage, FileSessionStorage

logger = logging.getLogger(__name__)


class AsyncPGBankClient:
    """Asynchronous PGBank client (one per account).

    Mirror of :class:`PGBankClient` using ``httpx.AsyncClient`` for transport.
    All methods that perform I/O are coroutines.

    Example:
        >>> import asyncio
        >>> from pgbank_unofficial import AsyncPGBankClient
        >>>
        >>> async def main():
        ...     async with AsyncPGBankClient(
        ...         username="alice", password="xxx", browser_id="bid_xxx"
        ...     ) as client:
        ...         await client.login()
        ...         balance = await client.get_balance()
        ...         print(balance.available)
        >>>
        >>> asyncio.run(main())
    """

    MID_LOGIN_STEP1 = PGBankClient.MID_LOGIN_STEP1
    MID_LOGIN_STEP2 = PGBankClient.MID_LOGIN_STEP2
    MID_GET_CUSTOMER_INFO = PGBankClient.MID_GET_CUSTOMER_INFO
    MID_GET_ACCOUNTS = PGBankClient.MID_GET_ACCOUNTS
    MID_GET_BALANCE = PGBankClient.MID_GET_BALANCE

    def __init__(
        self,
        username: str,
        password: str,
        browser_id: str,
        *,
        proxy: Optional[str] = None,
        session_path: Optional[str | Path] = None,
        session_storage: Optional[BaseSessionStorage] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        otp_provider: Callable[[str], str] = input,
        auto_login: bool = True,
    ) -> None:
        if not browser_id:
            raise MissingBrowserIDError("browser_id is required for PGBank authentication")
        if not username or not password:
            raise AuthenticationError(
                "username and password are required", reason="MISSING_CREDENTIALS"
            )

        self.username = username
        self.password = password
        self.browser_id = browser_id
        self.proxy = proxy
        self.session_path = Path(session_path) if session_path else None
        # Pluggable session storage; fall back to FileSessionStorage for convenience
        if session_storage is not None:
            self._session_storage: Optional[BaseSessionStorage] = session_storage
        elif self.session_path is not None:
            self._session_storage = FileSessionStorage(self.session_path)
        else:
            self._session_storage = None
        self.otp_provider = otp_provider
        self._timeout = timeout

        # Async HTTP client (lazy init so we don't require a running event loop)
        self._client: Optional[httpx.AsyncClient] = None

        # Mount config (sync fetch — happens once at init)
        # Use a sync httpx client for mount config fetch
        with httpx.Client(timeout=timeout) as temp_client:
            resp = temp_client.get(
                "https://ib.pgbank.com.vn/assets/mount/mount.json",
                headers={
                    "accept": "*/*",
                    "origin": ORIGIN,
                    "referer": ORIGIN + "/",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/145.0.0.0 Safari/537.36",
                },
            )
            self._mount = resp.json()
        self._default_token = self._extract_default_token(self._mount)
        self._default_server_pubkey = self._extract_server_pubkey(self._mount)
        self._hmac_key = self._mount.get("S23E1BQ45w", {}).get("HMAC", "pgomni20250323")

        # Per-account crypto keys
        self._private_key_pem, self._public_key_b64 = gen_keys()

        # Session state (mirrors sync client)
        self.token: str = self._default_token
        self.cif: Optional[str] = None
        self.account_no: str = ""
        self.client_id: str = ""
        self.user_id: str = ""
        self.session_id: str = ""
        self.full_name: str = ""
        self.mobile_no: str = ""
        self.server_pubkey: str = self._default_server_pubkey
        self.is_logged_in: bool = False
        self.login_message: str = ""

        self._otp_required: bool = False
        self._pending_otp_ref: str = ""
        self._pending_otp_token: str = ""

        # Public client version (for fingerprinting in requests)
        self.client_version = "145.0.0.0"
        self.platform = "Chrome"
        self.device_type = "WINDOWS"

        # Auto-login is deferred to a coroutine
        self._auto_login = auto_login
        if auto_login:
            # Note: auto_login on async client must be triggered by user via await self._auto_login()
            # We just record the intent here; the first I/O call will trigger it.
            pass

    def _extract_server_pubkey(self, mount: dict) -> str:
        from pgbank_unofficial._algorithm import _KEY_SERVER_PUBKEY

        for key in (_KEY_SERVER_PUBKEY, "serverPublicKey", "serverPubKey", "publicKey"):
            if key in mount:
                return mount[key]
        for v in mount.values():
            if isinstance(v, str) and len(v) > 100 and "BEGIN" not in v:
                return v
        raise PGBankError("could not find server public key in mount config")

    def _extract_default_token(self, mount: dict) -> str:
        from pgbank_unofficial._algorithm import _KEY_DEFAULT_TOKEN

        for key in (_KEY_DEFAULT_TOKEN, "defaultToken", "token", "bearer"):
            if key in mount:
                return mount[key]
        for v in mount.values():
            if isinstance(v, str) and 20 < len(v) < 200 and "BEGIN" not in v:
                return v
        raise PGBankError("could not find default token in mount config")

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                proxy=self.proxy,
            )
        return self._client

    def _post_headers(self, additional: Optional[dict] = None) -> dict[str, str]:
        h = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9,vi-VN;q=0.8,vi;q=0.7",
            "authorization": f"Bearer {self.token}",
            "content-type": "application/json",
            "origin": ORIGIN,
            "referer": ORIGIN + "/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36",
            "x-channel": "IB",
            "x-request-id": make_x_request_id(self.username),
        }
        if additional:
            h.update(additional)
        return h

    def _now_request_time(self) -> str:
        return datetime.now(VN_TZ).strftime("%Y%m%d%H%M%S")

    def _calc_checksum(self, payload: dict, fields: list[str]) -> str:
        import base64
        import hashlib
        import hmac

        value = "|".join(str(payload.get(field, "")) for field in fields)
        digest = hmac.new(self._hmac_key.encode(), value.encode(), hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    def _login_checksum_fields(self) -> list[str]:
        return ["userName", "password", "browserId", "requestTime"]

    def _prepare_payload(self, mid: str, payload: dict) -> dict:
        raw = dict(payload or {})
        raw.setdefault("checkSum", "")
        prepared = {
            **raw,
            "requestTime": raw.get("requestTime") or self._now_request_time(),
            "browserId": raw.get("browserId") or self.browser_id,
            "lang": raw.get("lang") or "VN",
            "mid": mid,
        }
        if self.session_id:
            prepared.update(
                {
                    "clientId": self.client_id,
                    "userId": self.user_id,
                    "cifNo": self.cif,
                    "sessionId": self.session_id,
                    "publicKeyIb": self.server_pubkey,
                    "keyIdIb": self.token,
                    "userName": self.username,
                }
            )
        return prepared

    def _server_pubkey_for_mid(self, mid: str) -> str:
        """Use mount-config default pubkey for pre-login MIDs, per-account after."""
        from pgbank_unofficial._params import DEFAULT_KEY_MIDS

        if mid in DEFAULT_KEY_MIDS:
            return self._default_server_pubkey
        return self.server_pubkey

    async def _post(self, service: str, mid: str, payload: dict) -> dict:
        """Async encrypted POST to PGBank API."""
        client = await self._ensure_client()
        url = f"{BASE_URL}/{service}/{mid}"
        prepared = self._prepare_payload(mid, payload)
        body = {k: v for k, v in prepared.items() if k not in ("mid",)}

        server_pubkey = self._server_pubkey_for_mid(mid)
        encrypted = encrypt_request(
            data=body,
            client_pub_key_str=self._public_key_b64,
            server_pub_key_base64=server_pubkey,
        )
        if not encrypted["d"] or not encrypted["k"]:
            raise PGBankError("encryption failed (empty d or k)")
        try:
            response = await client.post(url, json=encrypted, headers=self._post_headers())
        except httpx.TimeoutException as e:
            raise PGBankTimeoutError(f"request to {url} timed out after {self._timeout}s") from e
        response.raise_for_status()
        decoded = response.json()
        if isinstance(decoded, dict):
            res = decrypt_response(decoded, self._private_key_pem)
            code = str(res.get("code", ""))
            if code in ("98", "99"):
                raise SessionExpiredError(res.get("des", "session expired"), code=code)
            return res
        return decoded

    def _save_session(self) -> None:
        if self._session_storage is None:
            return
        data = {
            "token": self.token,
            "cif": self.cif,
            "clientId": self.client_id,
            "userId": self.user_id,
            "sessionId": self.session_id,
            "fullName": self.full_name,
            "mobileNo": self.mobile_no,
            "serverPubKey": self.server_pubkey,
        }
        try:
            self._session_storage.save_session(self.username, data)
        except Exception as e:
            logger.warning("failed to save session: %s", e)

    def _load_session(self) -> bool:
        if self._session_storage is None:
            return False
        try:
            data = self._session_storage.load_session(self.username)
        except Exception as e:
            logger.warning("failed to load session: %s", e)
            return False
        if not data or not data.get("sessionId"):
            return False
        self.token = data.get("token", self.token)
        self.cif = data.get("cif")
        self.client_id = data.get("clientId", "")
        self.user_id = data.get("userId", "")
        self.session_id = data.get("sessionId", "")
        self.full_name = data.get("fullName", "")
        self.mobile_no = data.get("mobileNo", "")
        self.server_pubkey = data.get("serverPubKey", self.server_pubkey)
        self.is_logged_in = True
        return True

    async def _restore_or_login(self) -> None:
        if self._load_session():
            return
        try:
            await self.login()
        except AuthenticationError as e:
            logger.warning("auto-login failed: %s", e)
            self.is_logged_in = False

    def _apply_session(self, data: dict) -> None:
        self.token = data.get("keyIdIb", data.get("token", self.token))
        self.cif = data.get("cifNo", data.get("cif"))
        self.client_id = str(data.get("clientId", ""))
        self.user_id = str(data.get("userId", ""))
        self.session_id = data.get("sessionId", "")
        self.full_name = data.get("fullName", "")
        self.mobile_no = data.get("mobileNo", "")
        new_pubkey = data.get("publicKeyIb")
        if new_pubkey:
            self.server_pubkey = new_pubkey
        self.is_logged_in = True
        self._save_session()

    # ── Auth ─────────────────────────────────────────────────────────────────

    async def login_step1(self) -> dict:
        """Step 1: send username + password. May return OTP challenge or sessionId."""
        request_time = self._now_request_time()
        payload = {
            "userName": self.username,
            "password": self.password,
            "lang": "VN",
            "browserId": self.browser_id,
            "isIncognito": 0,
            "requestTime": request_time,
            "DT": self.device_type,
            "PM": self.platform,
            "E": self.browser_id,
            "version": self.client_version,
        }
        payload["checkSum"] = self._calc_checksum(payload, self._login_checksum_fields())

        response = await self._post(SERVICE["AUTH"], MID["LOGIN"], payload)
        code = str(response.get("code", response.get("returnCode", "")))

        if code == "00":
            self._apply_session(response)
            self.login_message = "login success"
            logger.info("[PGBank] Login success (no OTP)")
        elif code in ("01", "114"):
            self._otp_required = True
            self._pending_otp_ref = response.get(
                "refNo", response.get("otpRefNo", response.get("txnToken", ""))
            )
            self._pending_otp_token = response.get("token", self._default_token)
            self.login_message = "otp_required"
            logger.info(f"[PGBank] OTP required (code {code})")
        elif code == "101":
            msg = response.get("des", response.get("message", "Invalid credentials"))
            self.login_message = msg
            raise AuthenticationError(msg, reason="INVALID_CREDENTIALS", code=code)
        else:
            msg = response.get("des", response.get("message", f"unknown code {code}"))
            self.login_message = msg
            raise PGBankError(f"login failed: {msg} (code {code})", code=code)
        return response

    async def login_step2(self, otp: str) -> dict:
        """Step 2: submit OTP to complete login."""
        if not self._otp_required:
            raise PGBankError("no pending OTP — call login_step1 first")
        import re

        otp_clean = re.sub(r"\D", "", str(otp or ""))
        if not otp_clean:
            raise AuthenticationError("empty OTP", reason="EMPTY_OTP")

        old_token = self.token
        self.token = self._pending_otp_token  # use temporary session token for OTP verification
        try:
            payload = {
                "otp": otp_clean,
                "refNo": self._pending_otp_ref,
                "txnToken": self._pending_otp_ref,
                "authenData": otp_clean,
                "userName": self.username,
            }
            response = await self._post(SERVICE["AUTH"], MID["CONFIRM_OTP"], payload)
            code = str(response.get("code", response.get("returnCode", "")))
            if code == "00":
                self._apply_session(response)
                self._otp_required = False
                self.login_message = "login success (otp confirmed)"
                logger.info("[PGBank] OTP confirmed. Session saved.")
            else:
                msg = response.get("des", response.get("message", "OTP failed"))
                self.login_message = msg
                raise AuthenticationError(msg, reason="OTP_FAILED", code=code)
            return response
        finally:
            if not self.is_logged_in:
                self.token = old_token

    async def login(self, otp: Optional[str] = None) -> dict:
        resp = await self.login_step1()
        if self._otp_required:
            otp_value = otp if otp is not None else self.otp_provider("Enter OTP: ")
            resp = await self.login_step2(otp_value)
        return resp

    async def submit_login_otp(self, otp: str) -> dict:
        return await self.login_step2(otp)

    # ── Queries ──────────────────────────────────────────────────────────────

    def _require_login(self) -> None:
        if not self.is_logged_in:
            raise PGBankError("not logged in — call login() first")

    async def get_accounts(self) -> list[BankAccount]:
        """Fetch the list of payment (checking) accounts."""
        self._require_login()
        from pgbank_unofficial._params import MID, SERVICE

        response = await self._post(SERVICE["BANK"], MID["GET_ACCOUNT_PAYMENTS"], {})
        accounts_data = response.get("data", response.get("listAccount", []))
        accounts = []
        for a in accounts_data:
            balance = a.get("availableBalance") or a.get("currentBalance") or "0"
            accounts.append(
                BankAccount(
                    account_number=str(a.get("accountNo", a.get("accountNumber", ""))),
                    account_name=a.get("custName", a.get("accountName", "")),
                    balance=Decimal(str(balance)),
                    currency=a.get("currency", "VND"),
                    account_type=a.get("accountTypeName", a.get("accountType", "checking")),
                )
            )
        return accounts

    async def get_account_info(self) -> AccountInfo:
        """Fetch the customer profile + primary account info."""
        self._require_login()
        from pgbank_unofficial._params import MID, SERVICE

        try:
            profile_resp = await self._post(SERVICE["UTILITY"], MID["GET_CUSTOMER_INFO"], {})
        except Exception:
            profile_resp = {}
        accounts = await self.get_accounts()
        primary = (
            accounts[0]
            if accounts
            else BankAccount(
                account_number=self.account_no,
                account_name=self.full_name,
                balance=Decimal("0"),
            )
        )
        cust_data = profile_resp.get("customer", {}) or {}
        cif_no = cust_data.get("cifNo") or profile_resp.get("cifNo") or self.cif or ""
        full_name = cust_data.get("fullName") or profile_resp.get("fullName") or self.full_name
        return AccountInfo(
            customer_id=cif_no,
            customer_name=full_name,
            accounts=accounts,
            primary_account=primary,
        )

    async def get_customer_info(self) -> AccountInfo:
        """Backward-compat alias for :meth:`get_account_info`."""
        return await self.get_account_info()

    async def get_savings_accounts(self) -> list[BankAccount]:
        """Fetch online + offline savings accounts (separate from checking)."""
        self._require_login()
        from pgbank_unofficial._params import MID, SERVICE

        response = await self._post(SERVICE["BANK"], MID["GET_ACCOUNT_SAVING"], {})
        all_savings = response.get("listSavingAccountOnline", []) + response.get(
            "listSavingAccountOffline", []
        )
        accounts = []
        for a in all_savings:
            balance = a.get("currentBalance") or a.get("availableBalance") or "0"
            accounts.append(
                BankAccount(
                    account_number=str(a.get("accountNo", "")),
                    account_name=a.get("custName", a.get("accountName", "")),
                    balance=Decimal(str(balance)),
                    currency=a.get("currency", "VND"),
                    account_type="savings",
                )
            )
        return accounts

    async def get_balance(self, account_number: Optional[str] = None) -> Balance:
        """Fetch live balance for an account (or default if None)."""
        self._require_login()
        from pgbank_unofficial._params import MID, SERVICE

        if not account_number:
            account_number = self.account_no or None
            if not account_number:
                accounts = await self.get_accounts()
                if not accounts:
                    raise PGBankError("no account specified and none found for this customer")
                account_number = accounts[0].account_number

        response = await self._post(
            SERVICE["BANK"],
            MID["AVAILABLE_BALANCE"],
            {"accountNumber": account_number},
        )
        if str(response.get("code", "")) not in ("00",):
            raise PGBankError(
                response.get("des", "balance fetch failed"),
                code=str(response.get("code", "")),
            )
        return Balance(
            account_number=response.get("accountNo", account_number),
            available=Decimal(str(response.get("availableBalance", "0"))),
            total=Decimal(
                str(response.get("currentBalance", response.get("availableBalance", "0")))
            ),
            currency=response.get("currency", "VND"),
            as_of=datetime.now(VN_TZ),
        )

    def _format_ib_date(self, value: Any) -> str:
        from datetime import date, datetime

        if isinstance(value, (datetime, date)):
            return value.strftime("%Y%m%d")
        text = str(value).strip()
        if len(text) == 8 and text.isdigit():
            return text
        if "/" in text:
            day, month, year = text.split("/")[:3]
            return f"{year.zfill(4)}{month.zfill(2)}{day.zfill(2)}"
        return text

    async def get_contacts(self) -> list[dict]:
        """Fetch the user's saved contacts (beneficiaries)."""
        self._require_login()
        from pgbank_unofficial._params import MID, SERVICE

        response = await self._post(SERVICE["UTILITY"], MID["GET_CONTACTS"], {"beneType": "1,2,3"})
        return response.get("listContact", [])

    async def create_contact(
        self,
        name: str,
        receiver_account: str,
        bank_code: str,
        bank_name: str,
        bene_name: str,
        bene_type: str = "2",
        favourite: bool = False,
    ) -> dict:
        """Create a new contact (beneficiary).

        Args:
            name: Nickname / display name.
            receiver_account: Recipient's account number or card number.
            bank_code: Target bank code (e.g. NAPAS bank code).
            bank_name: Target bank name (e.g. "Techcombank").
            bene_name: Full recipient name (fully capitalized).
            bene_type: Contact type ("1" for PGBank, "2" for NAPAS, "3" for CITAD).
            favourite: Whether to mark this contact as a favorite.

        Returns:
            The raw response dictionary from the server.
        """
        self._require_login()
        from pgbank_unofficial._params import MID, SERVICE

        payload = {
            "beneType": bene_type,
            "bankCode": bank_code,
            "bankName": bank_name,
            "name": name,
            "pan": receiver_account,
            "pgName": None,
            "beneName": bene_name,
            "favourite": favourite,
        }
        response = await self._post(SERVICE["UTILITY"], MID["CREATE_CONTACT"], payload)
        if str(response.get("code", "")) not in ("00",):
            raise PGBankError(
                response.get("des", "Contact creation failed"),
                code=str(response.get("code", "")),
            )
        return response

    async def update_contact(
        self,
        bene_id: str | int,
        name: Optional[str] = None,
        favourite: Optional[bool] = None,
        **extra_fields,
    ) -> dict:
        """Update an existing contact.

        Args:
            bene_id: The ID of the contact to update.
            name: Optional new nickname / display name.
            favourite: Optional boolean to mark/unmark as favorite.
            extra_fields: Other raw fields to update.

        Returns:
            The raw response dictionary from the server.
        """
        self._require_login()
        from pgbank_unofficial._params import MID, SERVICE

        payload = {
            "beneId": str(bene_id),
            **extra_fields,
        }
        if name is not None:
            payload["name"] = name
        if favourite is not None:
            payload["favourite"] = favourite
        response = await self._post(SERVICE["UTILITY"], MID["UPDATE_CONTACT"], payload)
        if str(response.get("code", "")) not in ("00",):
            raise PGBankError(
                response.get("des", "Contact update failed"),
                code=str(response.get("code", "")),
            )
        return response

    async def delete_contact(self, bene_ids: str | int | list[str | int]) -> dict:
        """Delete one or more contacts by their IDs.

        Args:
            bene_ids: A single ID (str/int), a list/tuple of IDs, or a comma-separated string of IDs.

        Returns:
            The raw response dictionary from the server.
        """
        self._require_login()
        from pgbank_unofficial._params import MID, SERVICE

        if isinstance(bene_ids, (list, tuple)):
            ids_str = ",".join(str(i) for i in bene_ids)
        else:
            ids_str = str(bene_ids)
        payload = {"beneIds": ids_str}
        response = await self._post(SERVICE["UTILITY"], MID["REMOVE_CONTACT"], payload)
        if str(response.get("code", "")) not in ("00",):
            raise PGBankError(
                response.get("des", "Contact deletion failed"),
                code=str(response.get("code", "")),
            )
        return response

    async def remove_contact(self, bene_ids: str | int | list[str | int]) -> dict:
        """Alias for :meth:`delete_contact`."""
        return await self.delete_contact(bene_ids)

    async def get_banks(self) -> list[dict]:
        """Fetch the list of banks supported by PGBank/NAPAS."""
        self._require_login()
        from pgbank_unofficial._params import MID, SERVICE

        response = await self._post(SERVICE["UTILITY"], MID["GET_LIST_BANK"], {})
        return response.get("banks", response.get("data", []))

    async def get_receiver_name(self, receiver_account: str, bank_code: str) -> str:
        """Resolve the receiver's name for domestic/CITAD or PGBank transfers."""
        self._require_login()
        from pgbank_unofficial._params import MID, SERVICE

        payload = {
            "identifier": receiver_account,
            "bankCode": bank_code,
            "beneficiaryName": "",
        }
        response = await self._post(SERVICE["BANK"], MID["GET_RECEIVER_NAME"], payload)
        if str(response.get("code", "")) not in ("00",):
            raise PGBankError(
                response.get("des", "Receiver name lookup failed"),
                code=str(response.get("code", "")),
            )
        return response.get("beneficiaryName", "")

    async def get_receiver_name_napas(
        self, source_account: str, receiver_account: str, bank_code: str
    ) -> str:
        """Resolve the receiver's name for NAPAS 24/7 fast transfers."""
        self._require_login()
        from pgbank_unofficial._params import MID, SERVICE

        payload = {
            "identifier": receiver_account,
            "bankCode": bank_code,
            "beneficiaryName": "",
            "sourceAccount": source_account,
        }
        response = await self._post(SERVICE["BANK"], MID["GET_RECEIVER_NAME_NAPAS"], payload)
        if str(response.get("code", "")) not in ("00",):
            raise PGBankError(
                response.get("des", "Receiver name lookup failed"),
                code=str(response.get("code", "")),
            )
        return response.get("beneficiaryName", "")

    async def get_transaction_history(
        self,
        account_number: str,
        from_date: str | datetime | date,
        to_date: str | datetime | date,
    ) -> list[Transaction]:
        """Fetch transaction history for a specific account."""
        self._require_login()
        from pgbank_unofficial._params import MID, SERVICE

        payload = {
            "accountNumber": account_number,
            "fromDate": self._format_ib_date(from_date),
            "toDate": self._format_ib_date(to_date),
        }
        response = await self._post(SERVICE["BANK"], MID["GET_TRANSACTION_HISTORY"], payload)
        if str(response.get("code", "")) not in ("00",):
            raise PGBankError(
                response.get("des", "Transaction history fetch failed"),
                code=str(response.get("code", "")),
            )

        tran_list = response.get("tranList", [])
        transactions = []
        for t in tran_list:
            raw_amt = str(t.get("AmountLCY", "0"))
            is_debit = raw_amt.startswith("-")
            amount = Decimal(raw_amt.lstrip("-"))
            direction = TransactionDirection.DEBIT if is_debit else TransactionDirection.CREDIT

            dt_str = t.get("Datetime", "")
            try:
                dt = datetime.strptime(dt_str, "%y-%m-%d %H:%M:%S").replace(tzinfo=VN_TZ)
            except Exception:
                dt = datetime.now(VN_TZ)

            transactions.append(
                Transaction(
                    id=str(t.get("MaGD", t.get("StmtID", ""))),
                    account_number=account_number,
                    type=direction,
                    amount=amount,
                    currency=t.get("ccy", "VND"),
                    counterparty_name="",
                    counterparty_account="",
                    counterparty_bank=None,
                    description=t.get("Narrative", ""),
                    timestamp=dt,
                    raw=t,
                )
            )
        return transactions

    async def get_transaction_detail(self, account_number: str, record_id: str) -> dict:
        """Fetch detailed information for a single transaction record."""
        self._require_login()
        from pgbank_unofficial._params import MID, SERVICE

        payload = {
            "accountNumber": account_number,
            "recordId": record_id,
        }
        response = await self._post(SERVICE["BANK"], MID["GET_DETAIL_TRANSACTION_HISTORY"], payload)
        if str(response.get("code", "")) not in ("00",):
            raise PGBankError(
                response.get("des", "Transaction detail fetch failed"),
                code=str(response.get("code", "")),
            )
        return response

    async def change_password(self, old_password: str, new_password: str) -> dict:
        """Change the account password (does not require OTP).

        Args:
            old_password: The current password.
            new_password: The new password.

        Returns:
            The raw response dictionary from the server.
        """
        self._require_login()
        from pgbank_unofficial._params import MID, SERVICE

        payload = {
            "oldPassword": old_password,
            "newPassword": new_password,
            "newPasswordVerify": new_password,
        }
        response = await self._post(SERVICE["AUTH"], MID["CHANGE_PASSWORD_AFTER_LOGIN"], payload)
        if str(response.get("code", "")) not in ("00",):
            raise PGBankError(
                response.get("des", "Password change failed"),
                code=str(response.get("code", "")),
            )
        self.password = new_password
        return response

    def logout(self) -> None:
        """Clear session state and delete persisted session (via storage backend)."""
        self.token = self._default_token
        self.cif = None
        self.account_no = ""
        self.client_id = ""
        self.user_id = ""
        self.session_id = ""
        self.full_name = ""
        self.mobile_no = ""
        self.server_pubkey = self._default_server_pubkey
        self.is_logged_in = False
        self._otp_required = False
        if self._session_storage is not None:
            try:
                self._session_storage.delete_session(self.username)
            except Exception:
                pass

    async def is_alive(self, *, retry: bool = True, timeout: Optional[float] = None) -> bool:
        """Check whether this account is alive (logged in + API reachable)."""
        try:
            accounts = await self.get_accounts()
            return bool(accounts) or self.is_logged_in
        except Exception:
            if retry and self.is_logged_in:
                try:
                    self.logout()
                    await self.login()
                    accounts = await self.get_accounts()
                    return bool(accounts)
                except Exception:
                    return False
            return False

    async def health_check(self) -> dict[str, Any]:
        """Detailed health snapshot — returns a dict for logging/monitoring."""
        result: dict[str, Any] = {
            "alive": False,
            "cif": self.cif,
            "full_name": self.full_name,
            "account_count": 0,
            "total_balance": "0",
            "currency": "VND",
            "last_error": None,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            accounts = await self.get_accounts()
            result["alive"] = True
            result["account_count"] = len(accounts)
            if accounts:
                total = sum((a.balance for a in accounts), Decimal("0"))
                result["total_balance"] = str(total)
                result["currency"] = accounts[0].currency
        except Exception as e:
            result["last_error"] = f"{type(e).__name__}: {e}"
        return result

    async def get_config(self) -> dict:
        """Fetch user preferences / config (background, smart-OTP, etc.)."""
        self._require_login()
        from pgbank_unofficial._params import MID, SERVICE

        return await self._post(SERVICE["UTILITY"], MID["GET_CONFIG"], {})

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> AsyncPGBankClient:
        if self._auto_login:
            await self._restore_or_login()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
