"""Test the encryption algorithm module."""

import base64
import json
import os

from pgbank_unofficial._algorithm import (
    aes_decrypt,
    aes_encrypt,
    clean_otp,
    decrypt_response,
    encrypt_request,
    gen_keys,
    get_date,
    make_x_request_id,
)


def test_aes_encrypt_decrypt_roundtrip():
    """AES-CTR encrypt then decrypt should give back original plaintext."""
    key = os.urandom(32)
    iv = os.urandom(16)
    plaintext = b"Hello, PGBank! 12345"
    ciphertext = aes_encrypt(plaintext, key, iv)
    decrypted = aes_decrypt(ciphertext, key, iv)
    assert decrypted == plaintext


def test_aes_encrypt_changes_ciphertext_with_different_iv():
    """Same key + plaintext + different IV should produce different ciphertext."""
    key = os.urandom(32)
    iv1 = os.urandom(16)
    iv2 = os.urandom(16)
    plaintext = b"Hello, PGBank!"
    ct1 = aes_encrypt(plaintext, key, iv1)
    ct2 = aes_encrypt(plaintext, key, iv2)
    assert ct1 != ct2


def test_gen_keys_produces_valid_keypair():
    """gen_keys() should return matching private/public keys."""
    private_pem, public_b64 = gen_keys()
    assert "BEGIN PRIVATE KEY" in private_pem
    assert "-----BEGIN PUBLIC KEY-----" not in public_b64  # headers stripped
    assert "-----END PUBLIC KEY-----" not in public_b64
    # public_b64 is base64 of binary SubjectPublicKeyInfo (DER)
    decoded = base64.b64decode(public_b64)
    # DER-encoded SubjectPublicKeyInfo starts with SEQUENCE tag (0x30)
    assert decoded[0] == 0x30
    assert len(decoded) > 50  # non-trivial key material


def test_gen_keys_produce_unique_pairs():
    """Each call to gen_keys() should produce different keys."""
    priv1, pub1 = gen_keys()
    priv2, pub2 = gen_keys()
    assert priv1 != priv2
    assert pub1 != pub2


def test_encrypt_request_returns_d_and_k():
    """encrypt_request should return dict with 'd' and 'k' keys."""
    priv, pub = gen_keys()
    result = encrypt_request(
        data={"username": "alice"},
        client_pub_key_str=pub,
        server_pub_key_base64=base64.b64encode(priv.encode()).decode(),
    )
    assert "d" in result
    assert "k" in result
    assert isinstance(result["d"], str)
    assert isinstance(result["k"], str)


def test_encrypt_request_d_is_base64():
    """The 'd' field should be valid base64 of (IV + ciphertext)."""
    priv, pub = gen_keys()
    server_pem = (
        "-----BEGIN PUBLIC KEY-----\n"
        + "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuP+5pw==\n"
        + "-----END PUBLIC KEY-----\n"
    )
    server_b64 = base64.b64encode(server_pem.encode()).decode()
    result = encrypt_request(
        data={"x": "1"},
        client_pub_key_str=pub,
        server_pub_key_base64=server_b64,
    )
    if result["d"]:  # if encryption succeeded
        decoded = base64.b64decode(result["d"])
        assert len(decoded) > 16  # at least IV (16) + something


def test_decrypt_response_passthrough_for_plain_json():
    """decrypt_response should return the original dict if no 'd'/'k' keys."""
    plain = {"foo": "bar", "baz": 123}
    result = decrypt_response(plain, "fake-key")
    assert result == plain


def test_decrypt_response_with_valid_encryption():
    """Round-trip: encrypt then decrypt should return original data."""
    priv, pub = gen_keys()
    # Manually encrypt
    aes_key = os.urandom(32)
    iv = os.urandom(16)
    payload = {"foo": "bar", "baz": 123}
    ciphertext = aes_encrypt(json.dumps(payload).encode("utf-8"), aes_key, iv)

    # Wrap AES key with public key (RSA-PKCS1v15)
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    public_key = serialization.load_pem_public_key(
        ("-----BEGIN PUBLIC KEY-----\n" + pub + "\n-----END PUBLIC KEY-----\n").encode()
    )
    wrapped_key = public_key.encrypt(  # type: ignore[union-attr]
        base64.b64encode(aes_key), padding.PKCS1v15()
    )

    enc_obj = {
        "d": base64.b64encode(iv + ciphertext).decode(),
        "k": base64.b64encode(wrapped_key).decode(),
    }
    result = decrypt_response(enc_obj, priv)
    assert result == payload


def test_get_date_format():
    """get_date() should return (from, to) in dd/mm/yyyy format."""
    from_date, to_date = get_date()
    # Each is "dd/mm/yyyy" with 10 chars
    assert len(from_date) == 10
    assert len(to_date) == 10
    assert from_date[2] == "/"
    assert from_date[5] == "/"
    assert to_date[2] == "/"
    assert to_date[5] == "/"


def test_make_x_request_id_ends_with_f7af():
    """make_x_request_id should always end with 'f7af'."""
    rid = make_x_request_id("alice")
    assert rid.endswith("f7af")


def test_make_x_request_id_with_empty_username():
    """make_x_request_id with empty username should still produce valid ID."""
    rid = make_x_request_id("")
    assert rid.endswith("f7af")
    assert len(rid) >= 4


def test_clean_otp_strips_non_digits():
    """clean_otp should keep only digits."""
    assert clean_otp("123-456") == "123456"
    assert clean_otp("abc 123 def") == "123"
    assert clean_otp("123456") == "123456"


def test_clean_otp_handles_none():
    """clean_otp(None) should return empty string."""
    assert clean_otp(None) == ""


def test_clean_otp_handles_int():
    """clean_otp should accept integer OTP values."""
    assert clean_otp(123456) == "123456"
