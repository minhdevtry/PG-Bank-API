"""Tests for the webhook dispatcher module."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pgbank_unofficial.webhook import (
    DeliveryRecord,
    Event,
    Subscription,
    WebhookDispatcher,
    _sign_payload,
)


VN_TZ = timezone(timedelta(hours=7))


# ──────────────────────────────────────────────────────────────────────────────
# Event dataclass
# ──────────────────────────────────────────────────────────────────────────────


class TestEvent:
    def test_event_has_required_fields(self):
        """Event should have type, timestamp, and data."""
        event = Event(
            type="transaction.created",
            timestamp=datetime.now(tz=VN_TZ),
            data={"amount": "100000"},
        )
        assert event.type == "transaction.created"
        assert event.data["amount"] == "100000"

    def test_event_id_is_auto_generated(self):
        """Event.id should be a UUID string by default."""
        event = Event(type="balance.changed", timestamp=datetime.now(tz=VN_TZ), data={})
        assert isinstance(event.id, str)
        assert len(event.id) == 36  # UUID4 format

    def test_event_id_can_be_overridden(self):
        """Event.id can be set explicitly."""
        event = Event(
            type="test",
            timestamp=datetime.now(tz=VN_TZ),
            data={},
            id="custom-id-123",
        )
        assert event.id == "custom-id-123"


# ──────────────────────────────────────────────────────────────────────────────
# Subscription dataclass
# ──────────────────────────────────────────────────────────────────────────────


class TestSubscription:
    def test_subscription_required_fields(self):
        """Subscription should require url."""
        sub = Subscription(url="https://example.com/webhook")
        assert sub.url == "https://example.com/webhook"
        assert sub.active is True
        assert sub.event_types is None  # None = all events
        assert sub.retry_attempts == 3

    def test_subscription_all_defaults(self):
        """All fields should have sensible defaults."""
        sub = Subscription(url="https://example.com/webhook")
        assert sub.secret is None
        assert sub.event_types is None
        assert sub.headers == {}
        assert sub.timeout == 10.0
        assert sub.retry_backoff == 2.0
        assert sub.active is True


# ──────────────────────────────────────────────────────────────────────────────
# HMAC signing
# ──────────────────────────────────────────────────────────────────────────────


class TestHMACSigning:
    def test_sign_payload_known_vector(self):
        """HMAC-SHA256 with known vector should produce correct digest."""
        payload = b'{"type":"test"}'
        secret = "super-secret-key"
        digest = _sign_payload(payload, secret)
        # Verify it's a valid hex string
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)
        # Verify it matches manual computation
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert digest == expected

    def test_sign_payload_empty_secret(self):
        """Empty secret should still produce a digest."""
        payload = b'{"event":"test"}'
        digest = _sign_payload(payload, "")
        assert len(digest) == 64

    def test_different_secrets_produce_different_signatures(self):
        """Same payload with different secrets should differ."""
        payload = b'{"data":1}'
        digest1 = _sign_payload(payload, "secret1")
        digest2 = _sign_payload(payload, "secret2")
        assert digest1 != digest2


# ──────────────────────────────────────────────────────────────────────────────
# WebhookDispatcher
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def dispatcher():
    """A fresh dispatcher instance."""
    return WebhookDispatcher()


class TestDispatcherSubscriptionManagement:
    def test_add_subscription_returns_unique_id(self, dispatcher):
        """add_subscription should return a unique string ID."""
        sub = Subscription(url="https://example.com/hook")
        id1 = dispatcher.add_subscription(sub)
        id2 = dispatcher.add_subscription(sub)
        assert isinstance(id1, str)
        assert id1 != id2

    def test_add_subscription_stores_subscription(self, dispatcher):
        """Added subscription should appear in list_subscriptions."""
        sub = Subscription(url="https://example.com/hook")
        dispatcher.add_subscription(sub)
        listed = dispatcher.list_subscriptions()
        assert any(s.url == "https://example.com/hook" for s in listed)

    def test_add_subscription_with_event_types_filter(self, dispatcher):
        """Subscription with event_types should be stored correctly."""
        sub = Subscription(
            url="https://example.com/hook",
            event_types=["transaction.created", "balance.changed"],
        )
        dispatcher.add_subscription(sub)
        assert sub.event_types == ["transaction.created", "balance.changed"]

    def test_remove_subscription_deletes_it(self, dispatcher):
        """remove_subscription should delete the subscription."""
        sub = Subscription(url="https://example.com/hook")
        sub_id = dispatcher.add_subscription(sub)
        dispatcher.remove_subscription(sub_id)
        assert sub_id not in {s.url for s in dispatcher.list_subscriptions()}

    def test_remove_subscription_keyerror_if_not_found(self, dispatcher):
        """remove_subscription should raise KeyError for unknown ID."""
        with pytest.raises(KeyError):
            dispatcher.remove_subscription("nonexistent-id")

    def test_pause_subscription_sets_inactive(self, dispatcher):
        """pause_subscription should set active=False."""
        sub = Subscription(url="https://example.com/hook")
        sub_id = dispatcher.add_subscription(sub)
        dispatcher.pause_subscription(sub_id)
        paused = next(s for s in dispatcher.list_subscriptions() if s.url == sub.url)
        assert paused.active is False

    def test_resume_subscription_sets_active(self, dispatcher):
        """resume_subscription should set active=True."""
        sub = Subscription(url="https://example.com/hook")
        sub_id = dispatcher.add_subscription(sub)
        dispatcher.pause_subscription(sub_id)
        dispatcher.resume_subscription(sub_id)
        resumed = next(s for s in dispatcher.list_subscriptions() if s.url == sub.url)
        assert resumed.active is True

    def test_list_subscriptions_returns_all(self, dispatcher):
        """list_subscriptions should return all subscriptions."""
        dispatcher.add_subscription(Subscription(url="https://a.com"))
        dispatcher.add_subscription(Subscription(url="https://b.com"))
        listed = dispatcher.list_subscriptions()
        assert len(listed) == 2


class TestDispatcherDispatchSync:
    def test_dispatch_sync_delivers_to_all_active_subscriptions(self, dispatcher):
        """dispatch_sync should call httpx for every active subscription."""
        dispatcher.add_subscription(Subscription(url="https://a.com"))
        dispatcher.add_subscription(Subscription(url="https://b.com"))

        event = Event(type="test.event", timestamp=datetime.now(tz=VN_TZ), data={})

        with patch("pgbank_unofficial.webhook.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_httpx.post.return_value = mock_response

            records = dispatcher.dispatch_sync(event)

        assert len(records) == 2
        assert all(r.success for r in records)
        assert mock_httpx.post.call_count == 2

    def test_dispatch_sync_skips_inactive_subscriptions(self, dispatcher):
        """Inactive subscriptions should not receive deliveries."""
        dispatcher.add_subscription(Subscription(url="https://a.com"))
        sub2_id = dispatcher.add_subscription(
            Subscription(url="https://b.com")
        )
        dispatcher.pause_subscription(sub2_id)

        event = Event(type="test.event", timestamp=datetime.now(tz=VN_TZ), data={})

        with patch("pgbank_unofficial.webhook.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_httpx.post.return_value = mock_response

            records = dispatcher.dispatch_sync(event)

        assert len(records) == 1
        assert records[0].subscription_url == "https://a.com"

    def test_dispatch_sync_event_type_filter(self, dispatcher):
        """Subscription with event_types filter should only receive matching events."""
        dispatcher.add_subscription(
            Subscription(url="https://a.com", event_types=["transaction.created"])
        )
        dispatcher.add_subscription(
            Subscription(url="https://b.com", event_types=["balance.changed"])
        )
        # Subscription with None event_types receives all
        dispatcher.add_subscription(Subscription(url="https://c.com"))

        event = Event(type="transaction.created", timestamp=datetime.now(tz=VN_TZ), data={})

        with patch("pgbank_unofficial.webhook.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_httpx.post.return_value = mock_response

            records = dispatcher.dispatch_sync(event)

        # a.com and c.com should receive; b.com should not
        assert len(records) == 2
        assert {r.subscription_url for r in records} == {"https://a.com", "https://c.com"}

    def test_dispatch_sync_includes_hmac_signature(self, dispatcher):
        """POST should include X-PGBank-Signature header when secret is set."""
        dispatcher.add_subscription(
            Subscription(url="https://a.com", secret="my-secret")
        )
        event = Event(type="test", timestamp=datetime.now(tz=VN_TZ), data={})

        with patch("pgbank_unofficial.webhook.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_httpx.post.return_value = mock_response

            dispatcher.dispatch_sync(event)

            call_kwargs = mock_httpx.post.call_args.kwargs
            headers = call_kwargs.get("headers", {})
            assert "X-PGBank-Signature" in headers
            expected_sig = _sign_payload(
                json.dumps({"type": "test", "data": {}, "id": event.id}, sort_keys=True).encode(),
                "my-secret",
            )
            assert headers["X-PGBank-Signature"] == expected_sig

    def test_dispatch_sync_retries_on_500(self, dispatcher):
        """500 errors should trigger retry attempts."""
        dispatcher.add_subscription(
            Subscription(url="https://a.com", retry_attempts=3, retry_backoff=1.0)
        )
        event = Event(type="test", timestamp=datetime.now(tz=VN_TZ), data={})

        with patch("pgbank_unofficial.webhook.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Server Error"
            mock_httpx.post.return_value = mock_response

            records = dispatcher.dispatch_sync(event)

        assert len(records) == 1
        assert records[0].success is False
        assert records[0].attempts == 3
        assert mock_httpx.post.call_count == 3

    def test_dispatch_sync_no_retry_on_400(self, dispatcher):
        """400 errors should NOT be retried (single attempt only)."""
        dispatcher.add_subscription(
            Subscription(url="https://a.com", retry_attempts=3)
        )
        event = Event(type="test", timestamp=datetime.now(tz=VN_TZ), data={})

        with patch("pgbank_unofficial.webhook.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "Bad Request"
            mock_httpx.post.return_value = mock_response

            records = dispatcher.dispatch_sync(event)

        assert len(records) == 1
        assert records[0].success is False
        assert records[0].attempts == 1  # No retry for 400

    def test_dispatch_sync_success_record(self, dispatcher):
        """Successful delivery should record status_code and response."""
        dispatcher.add_subscription(Subscription(url="https://a.com"))
        event = Event(type="test", timestamp=datetime.now(tz=VN_TZ), data={})

        with patch("pgbank_unofficial.webhook.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "Delivered!"
            mock_httpx.post.return_value = mock_response

            records = dispatcher.dispatch_sync(event)

        record = records[0]
        assert record.success is True
        assert record.status_code == 200
        assert record.response == "Delivered!"
        assert record.error is None

    def test_dispatch_sync_timeout_error(self, dispatcher):
        """Timeout should be recorded as a failure."""
        dispatcher.add_subscription(
            Subscription(url="https://a.com", retry_attempts=1)
        )
        event = Event(type="test", timestamp=datetime.now(tz=VN_TZ), data={})

        with patch("pgbank_unofficial.webhook.httpx") as mock_httpx:
            mock_httpx.post.side_effect = Exception("connection timeout")

            records = dispatcher.dispatch_sync(event)

        assert len(records) == 1
        assert records[0].success is False
        assert "timeout" in records[0].error

    def test_dispatch_sync_delivery_history(self, dispatcher):
        """Delivery records should be stored in history."""
        dispatcher.add_subscription(Subscription(url="https://a.com"))
        event = Event(type="test", timestamp=datetime.now(tz=VN_TZ), data={})

        with patch("pgbank_unofficial.webhook.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_httpx.post.return_value = mock_response

            dispatcher.dispatch_sync(event)

        history = dispatcher.get_delivery_history()
        assert len(history) == 1
        assert history[0].event_type == "test"

    def test_dispatch_sync_filter_by_sub_id(self, dispatcher):
        """get_delivery_history(sub_id=...) should filter correctly."""
        sub1_id = dispatcher.add_subscription(Subscription(url="https://a.com"))
        dispatcher.add_subscription(Subscription(url="https://b.com"))
        event = Event(type="test", timestamp=datetime.now(tz=VN_TZ), data={})

        with patch("pgbank_unofficial.webhook.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_httpx.post.return_value = mock_response

            dispatcher.dispatch_sync(event)

        history = dispatcher.get_delivery_history(sub_id=sub1_id)
        assert all(r.subscription_url == "https://a.com" for r in history)


class TestDiscordTelegramIntegrations:
    def test_register_discord(self, dispatcher):
        """register_discord should add a subscription with Discord formatter."""
        sub_id = dispatcher.register_discord("https://discord.com/api/webhooks/123", events=["test"])

        subs = dispatcher.list_subscriptions()
        assert len(subs) == 1
        sub = subs[0]
        assert sub.url == "https://discord.com/api/webhooks/123"
        assert sub.event_types == ["test"]
        assert sub.formatter is not None

        # Verify formatting output
        event = Event(type="test", timestamp=datetime(2026, 6, 23, 12, 0, 0), data={"balance": "500000"})
        payload = sub.formatter(event)
        assert "embeds" in payload
        embed = payload["embeds"][0]
        assert "PGBank Event: test" in embed["title"]
        assert embed["color"] == 3447003
        assert any(f["name"] == "balance" and f["value"] == "500000" for f in embed["fields"])

    def test_register_telegram(self, dispatcher):
        """register_telegram should add a subscription with Telegram formatter."""
        sub_id = dispatcher.register_telegram(
            bot_token="token123",
            chat_id="chat999",
            events=["test-event"],
            template="Custom: {{ type }} for ID {{ id }}"
        )

        subs = dispatcher.list_subscriptions()
        assert len(subs) == 1
        sub = subs[0]
        assert sub.url == "https://api.telegram.org/bottoken123/sendMessage"
        assert sub.event_types == ["test-event"]
        assert sub.formatter is not None

        # Verify formatting output
        event = Event(type="test-event", timestamp=datetime(2026, 6, 23, 12, 0, 0), data={"ok": "yes"}, id="evt-111")
        payload = sub.formatter(event)
        assert payload["chat_id"] == "chat999"
        assert "Custom: test-event for ID evt-111" in payload["text"]


class TestDispatcherPublicAPI:
    def test_public_api_exports(self):
        """All webhook symbols should be importable from top-level package."""
        from pgbank_unofficial import DeliveryRecord, Event, Subscription, WebhookDispatcher

        assert all(
            cls is not None
            for cls in [Event, Subscription, DeliveryRecord, WebhookDispatcher]
        )

    def test_dispatcher_default_max_concurrent(self, dispatcher):
        """Dispatcher should initialize with default max_concurrent_deliveries."""
        assert dispatcher._max_concurrent_deliveries == 4
