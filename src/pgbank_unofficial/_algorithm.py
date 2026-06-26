"""Cryptographic primitives for PGBank API requests/responses.

This module is pure crypto — no HTTP, no I/O. The HTTP transport lives in
:mod:`pgbank_unofficial.http`.

PGBank's encryption scheme (observed from network traffic):
- AES-CTR with 32-byte key and 16-byte IV
- IV prepended to ciphertext, both base64-encoded as ``d``
- AES key wrapped with RSA-PKCS1v15 using server's public key, base64-encoded as ``k``

References:
- See :func:`encrypt_request` and :func:`decrypt_response` for the full flow.
- This module is a typed, dependency-light port of the original
  ``pg/pgbank/pgbank/utils/_algorithm.py`` that uses ``cryptography`` (already
  in our deps) instead of ``pycryptodome``.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from random import random
from time import time
from typing import Any, Union

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# ── Constants ────────────────────────────────────────────────────────────────
VN_TZ = timezone(timedelta(hours=7))

BASE_URL = "https://api-ib.pgbank.com.vn"
MOUNT_URL = "https://ib.pgbank.com.vn/assets/mount/mount.json"
ORIGIN = "https://ib.pgbank.com.vn"

# ── mount.json key names (obfuscated in bundle) ───────────────────────────────
_KEY_SERVER_PUBKEY = "c2Vy78dmVyUHVibGljS2V522RGV71mYXVsdA"
_KEY_DEFAULT_TOKEN = "Z8GVm3Y2X3Vs11dFRva2Vu"


# ── Date helpers ──────────────────────────────────────────────────────────────


def get_date() -> tuple[str, str]:
    """Return (from_date, to_date) as dd/mm/yyyy, 30 days apart."""
    now = datetime.now(VN_TZ)
    to_date = now.strftime("%d/%m/%Y")
    from_date = (now - timedelta(days=30)).strftime("%d/%m/%Y")
    return from_date, to_date


# ── RSA helpers ───────────────────────────────────────────────────────────────


def gen_keys() -> tuple[str, str]:
    """Generate RSA 1024-bit keypair.

    Returns:
        Tuple of (private_key_pem, public_key_base64_stripped).
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )

    public_b64 = (
        public_pem.replace("-----BEGIN PUBLIC KEY-----", "")
        .replace("-----END PUBLIC KEY-----", "")
        .replace("\n", "")
    )
    return private_pem, public_b64


# ── AES-CTR helpers ───────────────────────────────────────────────────────────


def _aes_ctr_cipher(key: bytes, iv: bytes) -> Cipher:
    """Build an AES-CTR Cipher object.

    The 16-byte IV serves as the initial counter value (per PGBank convention).
    """
    return Cipher(algorithms.AES(key), modes.CTR(iv))


def aes_encrypt(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    """Encrypt plaintext using AES-CTR."""
    encryptor = _aes_ctr_cipher(key, iv).encryptor()
    return encryptor.update(plaintext) + encryptor.finalize()


def aes_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    """Decrypt ciphertext using AES-CTR."""
    decryptor = _aes_ctr_cipher(key, iv).decryptor()
    return decryptor.update(ciphertext) + decryptor.finalize()


# ── Request/Response crypto ───────────────────────────────────────────────────


def encrypt_request(
    data: dict[str, Any],
    client_pub_key_str: str,
    server_pub_key_base64: str,
) -> dict[str, str]:
    """Encrypt a request payload using PGBank's scheme.

    Args:
        data: Request payload fields to encrypt (will be merged with clientPubKey).
        client_pub_key_str: Client's public key (PEM, no headers) — server needs this.
        server_pub_key_base64: Server's public key (base64-encoded PEM).

    Returns:
        Dict with ``d`` (encrypted payload, base64) and ``k`` (wrapped AES key, base64).

    Note:
        On any error, returns ``{"d": "", "k": ""}`` for compatibility with the
        original implementation. Callers should treat empty ``d``/``k`` as failure.
    """
    try:
        aes_key = os.urandom(32)
        iv = os.urandom(16)

        payload: dict[str, Any] = {"clientPubKey": client_pub_key_str, **data}
        ciphertext = aes_encrypt(json.dumps(payload).encode("utf-8"), aes_key, iv)
        d_base64 = base64.b64encode(iv + ciphertext).decode()

        server_pem = base64.b64decode(server_pub_key_base64).decode()
        server_key = serialization.load_pem_public_key(server_pem.encode())
        # Mypy can't narrow cryptography's public key union to RSAPublicKey;
        # runtime validation ensures it's RSA (server_pub_key_base64 is RSA pubkey).
        encrypted_key = server_key.encrypt(  # type: ignore[union-attr]
            base64.b64encode(aes_key),
            padding.PKCS1v15(),
        )
        k_base64 = base64.b64encode(encrypted_key).decode()

        return {"d": d_base64, "k": k_base64}
    except Exception:
        return {"d": "", "k": ""}


def decrypt_response(enc_obj: dict[str, Any], private_key_pem: str) -> dict[str, Any]:
    """Decrypt a response from PGBank.

    Args:
        enc_obj: Response dict, expected to have ``d`` and ``k`` keys.
        private_key_pem: Client's private key (PEM) used during the request.

    Returns:
        Decrypted JSON dict, or the original ``enc_obj`` if it doesn't have ``d``/``k``
        (plain JSON response, no encryption).
    """
    if "k" not in enc_obj or "d" not in enc_obj:
        return enc_obj

    k = base64.b64decode(enc_obj["k"])
    d = base64.b64decode(enc_obj["d"])

    private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    # PKCS1v15 decryption in cryptography lib doesn't take a sentinel; raises
    # ValueError on failure (callers should catch and handle).
    aes_key_b64 = private_key.decrypt(k, padding.PKCS1v15())  # type: ignore[union-attr]
    aes_key = base64.b64decode(aes_key_b64)

    iv = d[:16]
    data = d[16:]
    return json.loads(aes_decrypt(data, aes_key, iv).decode("utf-8"))


# ── Header helpers ────────────────────────────────────────────────────────────


def make_x_request_id(username: str = "") -> str:
    """Generate a request ID in the format PGBank expects.

    Observed format: ``<millis><2 random digits><crc16hex(username)>f7af``
    Example: ``178038511717027f7af``

    Note: This uses a hand-rolled CRC-16, not a real library (matching the
    original implementation's behavior).
    """
    millis = str(int(time() * 1000))
    rand_part = str(int(random() * 100)).zfill(2)
    crc_val = format(_crc16((username or "").encode()), "x")
    return millis + rand_part + crc_val + "f7af"


def _crc16(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    """Standard CRC-16/CCITT-FALSE implementation (poly=0x1021, init=0xFFFF)."""
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ poly
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


def clean_otp(value: Union[str, int, None]) -> str:
    """Normalize OTP: keep only digits, strip whitespace and other characters."""
    if value is None:
        return ""
    import re

    return re.sub(r"\D", "", str(value))


# ── Mount config helpers (HTTP-free, return placeholders) ─────────────────────

# The actual mount config fetch lives in :mod:`pgbank_unofficial.http`.
# This module just exposes the key names so other parts of the library can
# reference them without importing curl_cffi or requests.


def get_server_pubkey_from_mount(mount: dict[str, Any]) -> str:
    """Extract server public key (base64) from a loaded mount config dict."""
    return mount[_KEY_SERVER_PUBKEY]


def get_default_token_from_mount(mount: dict[str, Any]) -> str:
    """Extract default Bearer token from a loaded mount config dict."""
    return mount[_KEY_DEFAULT_TOKEN]
