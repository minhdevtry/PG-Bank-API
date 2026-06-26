"""Test that all public API symbols are importable from top-level package."""


def test_import_account():
    from pgbank_unofficial import Account

    assert Account is not None


def test_import_balance():
    from pgbank_unofficial import Balance

    assert Balance is not None


def test_import_transaction():
    from pgbank_unofficial import Transaction

    assert Transaction is not None


def test_import_transfer_result():
    from pgbank_unofficial import TransferResult

    assert TransferResult is not None


def test_import_pgbank_client():
    from pgbank_unofficial import PGBankClient

    assert PGBankClient is not None


def test_import_async_pgbank_client():
    from pgbank_unofficial import AsyncPGBankClient

    assert AsyncPGBankClient is not None


def test_import_exceptions():
    from pgbank_unofficial import (
        AuthenticationError,
        MissingBrowserIDError,
        PGBankError,
        SessionExpiredError,
        TimeoutError,
    )

    assert all(
        cls is not None
        for cls in [
            PGBankError,
            AuthenticationError,
            SessionExpiredError,
            MissingBrowserIDError,
            TimeoutError,
        ]
    )


def test_version_exists():
    import pgbank_unofficial

    assert hasattr(pgbank_unofficial, "__version__")
    assert pgbank_unofficial.__version__ == "0.2.0"


def test_import_storage_classes():
    from pgbank_unofficial import (
        BaseSessionStorage,
        BaseAsyncSessionStorage,
        FileSessionStorage,
        DirSessionStorage,
        MemorySessionStorage,
    )

    assert all(
        cls is not None
        for cls in [
            BaseSessionStorage,
            BaseAsyncSessionStorage,
            FileSessionStorage,
            DirSessionStorage,
            MemorySessionStorage,
        ]
    )
