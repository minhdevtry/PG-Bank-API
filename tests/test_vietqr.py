"""Tests for the VietQR generator module."""

from __future__ import annotations

import pytest

from pgbank_unofficial.vietqr import (
    VietQR,
    _crc16_ccitt_false,
    _tlv,
    _build_merchant_account_info,
    parse_qr,
    ParsedQR,
    _parse_tlv,
)


class TestTLVHelpers:
    """Verify EMVCo TLV construction and checksums."""

    def test_tlv_construction(self):
        """TLV should format tag, length, and value correctly."""
        assert _tlv("00", "01") == "000201"
        assert _tlv("01", "12") == "010212"
        assert _tlv("52", "0000") == "52040000"

        with pytest.raises(ValueError):
            _tlv("0", "val")  # tag too short
        with pytest.raises(ValueError):
            _tlv("000", "val")  # tag too long

    def test_crc16_ccitt_false(self):
        """CRC16 should match known check values."""
        # Known test vectors for CRC-16/CCITT-FALSE
        assert _crc16_ccitt_false("123456789") == "29B1"
        assert _crc16_ccitt_false("A") == "B915"


class TestVietQRBuilder:
    """Verify VietQR class correctly generates payloads."""

    def test_static_qr(self):
        """Static QR should omit amount and description in sub-tags."""
        qr = VietQR(
            bank_bin="970430",
            account_number="2883621213010",
            account_name="NGUYEN VAN A",
        )
        payload = qr.build()

        assert payload.startswith("000201010211")  # static initiation indicator
        assert "970430" in payload
        assert "2883621213010" in payload
        assert "NGUYEN VAN A" in payload
        # Verify CRC exists at the end
        assert len(payload) > 50
        assert payload[-4:] == _crc16_ccitt_false(payload[:-4])

    def test_dynamic_qr(self):
        """Dynamic QR should include amount and description in tags."""
        qr = VietQR(
            bank_bin="970430",
            account_number="1234567890",
            account_name="SHOP ABC",
            amount="50000",
            description="Bill 123",
            dynamic=True,
        )
        payload = qr.build()

        assert payload.startswith("000201010212")  # dynamic initiation indicator
        assert "50000" in payload
        assert "Bill 123" in payload
        assert payload[-4:] == _crc16_ccitt_false(payload[:-4])

    def test_image_url_generation(self):
        """image_url should return a correct img.vietqr.io URL."""
        qr = VietQR(
            bank_bin="970430",
            account_number="2883621213010",
            account_name="NGUYEN VAN A",
            amount="100000",
            description="Chuyen khoan",
        )
        url = qr.image_url()
        assert "img.vietqr.io" in url
        assert "2883621213010" in url
        assert "amount=100000" in url
        assert "addInfo=Chuyen%20khoan" in url or "addInfo=Chuyen+khoan" in url
        assert "accountName=NGUYEN%20VAN%20A" in url or "accountName=NGUYEN+VAN+A" in url


class TestVietQRParser:
    """Verify VietQR payload parsing works correctly."""

    def test_parse_tlv_basic(self):
        """Should parse TLV data into dict correctly (base 10 length)."""
        data = "000201010211"
        res = _parse_tlv(data)
        assert res == {"00": "01", "01": "11"}

        # Length > 10 (base 10 test)
        # tag "26", length "15" (15 chars), value "A00000072712345"
        data_long = "2615A00000072712345"
        res_long = _parse_tlv(data_long)
        assert res_long == {"26": "A00000072712345"}

    def test_parse_static_qr_roundtrip(self):
        """Static QR build and parse should yield identical fields."""
        qr = VietQR(
            bank_bin="970430",
            account_number="2883621213010",
            account_name="NGUYEN VAN A",
        )
        payload = qr.build()
        parsed = parse_qr(payload)

        assert parsed.bank_bin == "970430"
        assert parsed.account_number == "2883621213010"
        assert parsed.account_name == "NGUYEN VAN A"
        assert parsed.amount is None
        assert parsed.description is None
        assert parsed.dynamic is False

    def test_parse_dynamic_qr_roundtrip(self):
        """Dynamic QR build and parse should yield identical fields including amount and description."""
        qr = VietQR(
            bank_bin="970430",
            account_number="1234567890",
            account_name="SHOP ABC",
            amount="50000",
            description="Thanh toan hoa don dài hơn 10 ký tự",
            dynamic=True,
        )
        payload = qr.build()
        parsed = parse_qr(payload)

        assert parsed.bank_bin == "970430"
        assert parsed.account_number == "1234567890"
        assert parsed.account_name == "SHOP ABC"
        assert parsed.amount == "50000"
        assert parsed.description == "Thanh toan hoa don dài hơn 10 ký tự"
        assert parsed.dynamic is True

    def test_parse_invalid_crc(self):
        """Invalid CRC should raise ValueError."""
        qr = VietQR(
            bank_bin="970430",
            account_number="2883621213010",
            account_name="NGUYEN VAN A",
        )
        payload = qr.build()
        # Tamper with the CRC (last 4 characters)
        malformed_payload = payload[:-4] + "0000"
        with pytest.raises(ValueError, match="CRC mismatch"):
            parse_qr(malformed_payload)

    def test_parse_empty_or_malformed(self):
        """Empty or malformed payload should raise ValueError."""
        with pytest.raises(ValueError, match="empty QR payload"):
            parse_qr("")
        with pytest.raises(ValueError):
            parse_qr("123")  # too short
