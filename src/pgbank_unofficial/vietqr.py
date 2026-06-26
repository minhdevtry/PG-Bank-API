"""VietQR generator — EMVCo Merchant Presented QR (Vietnamese standard).

Implements the **VietQR** standard (NAPAS/State Bank of Vietnam spec) for
generating QR codes that:

1. **Receive money (static):** Anyone scanning the QR pays the amount they
   choose into the recipient's account.
2. **Pay a merchant (dynamic):** QR contains a fixed amount and description.
3. **Display as image:** Uses ``img.vietqr.io`` for zero-dep image generation,
   OR generates QR locally with ``qrcode`` if installed.

Reference spec: <https://vietqr.net/portal-service/download/documents/QR_Format_T&C_v1.0_VN.pdf>
EMVCo base: ISO/IEC 18004 (QR), EMVCo Merchant Presented QR spec.

Why we built our own (rather than just calling img.vietqr.io):

    The reference project only used the image API. We do the same (for the
    quick path) but ALSO generate the raw EMVCo payload + local QR images,
    so the library is:
    - **Offline-capable** (no img.vietqr.io roundtrip required)
    - **Auditable** (you see exactly what bytes go into the QR)
    - **Testable** (parse + round-trip without network)
    - **Embeddable** (return PNG bytes for in-memory rendering)

EMVCo payload structure (TLV format: tag-length-value, 2-char hex tag,
2-char hex length, value):

    00  02 "01"                      Payload Format Indicator
    01  02 "11" or "12"              Point of Initiation (11=static, 12=dynamic)
    26  NN <Merchant Account Info>   VietQR nested data (see below)
    52  04 "0000"                    Merchant Category Code
    53  03 "704"                     Transaction Currency (704 = VND)
    54  NN <amount>                  Transaction Amount (optional)
    58  02 "VN"                      Country Code
    59  NN <merchant name>           Merchant Name (max 25)
    60  NN <city>                    Merchant City (max 15)
    62  NN <additional data>         Optional (bill number, store label, etc.)
    63  04 <CRC-CCITT-FALSE>         CRC checksum (mandatory)
"""

from __future__ import annotations

import io
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

# ── VietQR-specific constants ───────────────────────────────────────────────

VIETNAM_COUNTRY_CODE = "VN"
VIETNAM_CURRENCY_CODE = "704"  # ISO 4217 — Vietnamese Dong
VIETQR_GUID = "A000000727"  # NAPAS Global Unique Identifier


# ── EMVCo TLV helpers ────────────────────────────────────────────────────────


def _tlv(tag: str, value: str) -> str:
    """EMVCo TLV: 2-hex-digit tag, 2-hex-digit length, value."""
    if len(tag) != 2:
        raise ValueError(f"TLV tag must be 2 chars, got {tag!r}")
    return f"{tag}{len(value):02d}{value}"


def _crc16_ccitt_false(data: str) -> str:
    """CRC-16/CCITT-FALSE — polynomial 0x1021, init 0xFFFF, no reflection.

    Required as the last 4 hex digits of every VietQR payload (Tag 63).
    Reference: <https://en.wikipedia.org/wiki/Cyclic_redundancy_check>
    """
    # Convert ASCII string to bytes
    crc = 0xFFFF
    for ch in data:
        crc ^= ord(ch) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return f"{crc:04X}"


# ── VietQR Merchant Account Information (Tag 26) ───────────────────────────


def _build_merchant_account_info(
    bank_bin: str,
    account_number: str,
    *,
    amount: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """Build Tag 26 (Merchant Account Information) payload for VietQR.

    Sub-tags inside Tag 26 (NAPAS-specific):

        00  GUID ("A000000727")
        01  Bank BIN code (6 digits)
        02  Account number (max 19)
        03  Amount (only for dynamic QR — if specified)
        04  Description / payment purpose (max 50)
        05  Reserved (NAPAS-specific, optional)
        06  Service code (NAPAS-specific, optional)
        07  Purpose code (NAPAS-specific, optional)
        08  Reserved (NAPAS-specific, optional)
    """
    parts = [
        _tlv("00", VIETQR_GUID),
        _tlv("01", str(bank_bin)),
        _tlv("02", str(account_number)),
    ]
    if amount:
        parts.append(_tlv("03", str(amount)))
    if description:
        # Limit to 50 chars (NAPAS spec)
        desc = description[:50]
        parts.append(_tlv("04", desc))
    return _tlv("26", "".join(parts))


# ── Main builder ────────────────────────────────────────────────────────────


@dataclass
class VietQR:
    """Builder for VietQR-compliant QR payloads.

    Two usage patterns:

    Static QR (for receiving money — most common):

        >>> qr = VietQR(bank_bin="970430", account_number="2883621213010",
        ...             account_name="NGUYEN VAN A")
        >>> qr.build()  # raw EMVCo string
        '00020101021126...'

    Dynamic QR (for paying a specific merchant):

        >>> qr = VietQR(bank_bin="970436", account_number="1234567890",
        ...             account_name="SHOP ABC", amount="50000",
        ...             description="Thanh toan don hang #123",
        ...             dynamic=True)
        >>> qr.build()

    Image generation (requires ``qrcode`` library):

        >>> qr.to_png_bytes()  # PNG bytes for the QR image
        b'\\x89PNG...'

    Online image via img.vietqr.io (zero deps):

        >>> qr.image_url()
        'https://img.vietqr.io/image/PGBank-2883621213010-compact2.png?accountName=...'
    """

    bank_bin: str
    account_number: str
    account_name: str
    amount: Optional[str] = None
    description: Optional[str] = None
    dynamic: bool = False  # True = dynamic (with amount), False = static
    category_code: str = "0000"  # MCC — 0000 = unclassified
    city: str = "Ho Chi Minh"  # Default — should be customized per merchant
    store_label: Optional[str] = None  # Goes into Tag 62-05
    terminal_label: Optional[str] = None  # Goes into Tag 62-07

    # Internal computed value (cache)
    _cached_payload: Optional[str] = field(default=None, init=False, repr=False)

    # ── Building ─────────────────────────────────────────────────────────

    def build(self) -> str:
        """Build the raw EMVCo payload string with valid CRC.

        Returns the full TLV-encoded string ready to be encoded as a QR code.
        """
        if self._cached_payload:
            return self._cached_payload

        # Tag 01: Point of Initiation Method
        #   11 = static (no amount specified, customer chooses)
        #   12 = dynamic (amount is specified, fixed payment)
        # If amount is set, force dynamic regardless of self.dynamic
        is_dynamic = self.dynamic or self.amount
        initiation = "12" if is_dynamic else "11"

        parts = [
            _tlv("00", "01"),  # Payload Format Indicator
            _tlv("01", initiation),
            _build_merchant_account_info(
                self.bank_bin,
                self.account_number,
                amount=str(self.amount) if is_dynamic else None,
                description=self.description if is_dynamic else None,
            ),
            _tlv("52", self.category_code),
            _tlv("53", VIETNAM_CURRENCY_CODE),
        ]

        if is_dynamic and self.amount:
            parts.append(_tlv("54", str(self.amount)))

        parts.extend(
            [
                _tlv("58", VIETNAM_COUNTRY_CODE),
                _tlv("59", self.account_name[:25]),  # Max 25 chars per spec
                _tlv("60", self.city[:15]),  # Max 15 chars per spec
            ]
        )

        # Tag 62: Additional Data Field (optional but useful)
        if self.store_label or self.terminal_label:
            additional = ""
            if self.store_label:
                additional += _tlv("05", self.store_label[:25])
            if self.terminal_label:
                additional += _tlv("07", self.terminal_label[:15])
            parts.append(_tlv("62", additional))

        # Tag 63: CRC checksum (computed over all preceding data + tag 63 + length)
        body = "".join(parts) + "6304"
        crc = _crc16_ccitt_false(body)
        full = body + crc

        self._cached_payload = full
        return full

    # ── Convenience outputs ──────────────────────────────────────────────

    def image_url(self, template: str = "compact2") -> str:
        """Build img.vietqr.io URL — works without any local QR library.

        Templates:
            - compact: minimal info (logo + 4 fields)
            - compact2: slightly larger with account holder name (default)
            - print: detailed layout for printed materials
        """
        bank_name = self._bank_bin_to_name(self.bank_bin)
        base = f"https://img.vietqr.io/image/" f"{bank_name}-{self.account_number}-{template}.png"
        params = []
        if self.amount:
            params.append(f"amount={self.amount}")
        if self.description:
            params.append(f"addInfo={urllib.parse.quote(self.description)}")
        if self.account_name:
            params.append(f"accountName={urllib.parse.quote(self.account_name)}")
        if params:
            base += "?" + "&".join(params)
        return base

    def to_png_bytes(self, error_correction: str = "M", box_size: int = 10) -> bytes:
        """Generate QR code as PNG bytes (requires ``qrcode`` library).

        Error correction levels (per EMVCo spec):
            - L: 7% (smallest QR)
            - M: 15% (recommended default)
            - Q: 25%
            - H: 30% (most robust, largest QR)
        """
        try:
            import qrcode  # type: ignore
            from qrcode.constants import (  # type: ignore
                ERROR_CORRECT_H,
                ERROR_CORRECT_L,
                ERROR_CORRECT_M,
                ERROR_CORRECT_Q,
            )
        except ImportError as e:
            raise ImportError(
                "qrcode library required for to_png_bytes(). "
                "Install with: pip install qrcode[pil]"
            ) from e

        ec_map = {
            "L": ERROR_CORRECT_L,
            "M": ERROR_CORRECT_M,
            "Q": ERROR_CORRECT_Q,
            "H": ERROR_CORRECT_H,
        }
        qr = qrcode.QRCode(
            error_correction=ec_map.get(error_correction, ERROR_CORRECT_M),
            box_size=box_size,
            border=4,
        )
        qr.add_data(self.build())
        qr.make(fit=True)

        # Try PIL, fall back to png-only
        try:
            from PIL import Image  # type: ignore # noqa: F401

            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except ImportError:
            # qrcode >= 7.x has a pure-PNG factory
            factory = qrcode.image.pure.PyPNGImage
            img = qr.make_image(image_factory=factory)
            buf = io.BytesIO()
            img.save(buf)
            return buf.getvalue()

    def to_terminal(self) -> str:
        """Print QR payload to terminal using Unicode half-block characters.

        Useful for debugging in a terminal without a graphics library.
        """
        return _render_terminal_qr(self.build())

    # ── Static helpers ───────────────────────────────────────────────────

    @staticmethod
    def _bank_bin_to_name(bin_code: str) -> str:
        """Convert a 6-digit bank BIN code to img.vietqr.io bank slug."""
        from pgbank_unofficial._params import BankCode

        # Reverse lookup — BankCode class is structured as constants
        for attr in dir(BankCode):
            if attr.startswith("_"):
                continue
            value = getattr(BankCode, attr)
            if value == bin_code:
                return attr.upper()
        return bin_code

    # ── Dunder ───────────────────────────────────────────────────────────

    def __str__(self) -> str:
        return self.build()

    def __repr__(self) -> str:
        kind = "dynamic" if (self.dynamic or self.amount) else "static"
        return (
            f"VietQR({kind} {self.bank_bin}/{self.account_number} "
            f"name={self.account_name!r} amount={self.amount!r})"
        )


# ── Parsing ─────────────────────────────────────────────────────────────────


@dataclass
class ParsedQR:
    """Parsed VietQR payload — useful for the 'pay merchant' flow."""

    bank_bin: str
    account_number: str
    account_name: str
    amount: Optional[str] = None
    description: Optional[str] = None
    dynamic: bool = False
    currency: str = "VND"
    country: str = "VN"
    city: str = ""
    raw: str = ""

    def to_vietqr(self) -> "VietQR":
        """Re-build a VietQR object from the parsed data."""
        return VietQR(
            bank_bin=self.bank_bin,
            account_number=self.account_number,
            account_name=self.account_name,
            amount=self.amount,
            description=self.description,
            dynamic=self.dynamic,
            city=self.city or "Ho Chi Minh",
        )


def parse_qr(payload: str) -> ParsedQR:
    """Parse an EMVCo QR payload into structured data.

    Supports any EMVCo-compliant QR (VietQR is a specific profile of EMVCo).

    Raises:
        ValueError: if payload is malformed or CRC is invalid.
    """
    if not payload or len(payload) < 4:
        raise ValueError("empty QR payload")
    # Validate CRC (last 4 hex chars)
    expected_crc = _crc16_ccitt_false(payload[:-4])
    actual_crc = payload[-4:]
    if expected_crc != actual_crc:
        raise ValueError(f"CRC mismatch: expected {expected_crc}, got {actual_crc}")

    parsed = _parse_tlv(payload[:-4])

    # Required: Tag 26 contains VietQR-specific merchant account info
    if "26" not in parsed:
        raise ValueError("missing Tag 26 (Merchant Account Information)")

    mai = _parse_tlv(parsed["26"])
    if "00" not in mai or mai["00"] != VIETQR_GUID:
        raise ValueError(f"missing VietQR GUID (expected {VIETQR_GUID}, got {mai.get('00', '?')})")

    bank_bin = mai.get("01", "")
    account_number = mai.get("02", "")
    amount = mai.get("03") or None
    description = mai.get("04") or None

    initiation = parsed.get("01", "11")
    return ParsedQR(
        bank_bin=bank_bin,
        account_number=account_number,
        account_name=parsed.get("59", ""),
        amount=amount,
        description=description,
        dynamic=initiation == "12",
        currency=parsed.get("53", "704"),
        country=parsed.get("58", "VN"),
        city=parsed.get("60", ""),
        raw=payload,
    )


def _parse_tlv(data: str) -> dict[str, str]:
    """Parse TLV (tag-length-value) into a dict."""
    result: dict[str, str] = {}
    i = 0
    while i < len(data):
        tag = data[i : i + 2]
        i += 2
        length = int(data[i : i + 2])
        i += 2
        value = data[i : i + length]
        i += length
        result[tag] = value
    return result


# ── Terminal rendering ─────────────────────────────────────────────────────


def _render_terminal_qr(payload: str) -> str:
    """Render QR payload to terminal using Unicode half-block characters.

    Uses a minimal pure-Python QR encoder (slower but zero deps).
    For high-volume use, install ``qrcode`` and use ``to_png_bytes()``.
    """
    # Lazy import to keep module import fast
    try:
        import qrcode  # type: ignore

        qr = qrcode.QRCode(border=1, box_size=1)
        qr.add_data(payload)
        qr.make(fit=True)
        matrix = qr.modules
        lines = []
        for y in range(0, len(matrix), 2):
            line = ""
            for x in range(len(matrix[0])):
                top = matrix[y][x] if y < len(matrix) else False
                bottom = matrix[y + 1][x] if y + 1 < len(matrix) else False
                if top and bottom:
                    line += "█"
                elif top:
                    line += "▀"
                elif bottom:
                    line += "▄"
                else:
                    line += " "
            lines.append(line)
        return "\n".join(lines)
    except ImportError:
        return f"[qrcode library not installed — payload only]\n" f"{payload}"
