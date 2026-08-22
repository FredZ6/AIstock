from stock_platform.infrastructure.observability.redaction import redact


def test_redaction_removes_credentials_prompts_addresses_and_untrusted_text() -> None:
    payload = {
        "authorization": "Bearer super-secret",
        "api_key": "provider-key",
        "prompt": "system prompt includes password=hunter2",
        "recipient_email": "analyst@example.com",
        "notification_address": "chat:123456",
        "provider_payload": {"headline": "untrusted full article body"},
        "safe": {"provider": "fixture", "status": "degraded"},
    }

    assert redact(payload) == {
        "authorization": "[REDACTED]",
        "api_key": "[REDACTED]",
        "prompt": "[REDACTED]",
        "recipient_email": "[REDACTED]",
        "notification_address": "[REDACTED]",
        "provider_payload": "[REDACTED]",
        "safe": {"provider": "fixture", "status": "degraded"},
    }


def test_redaction_handles_secret_values_nested_in_sequences() -> None:
    assert redact([{"access_token": "abc"}, "Bearer abc", "safe"]) == [
        {"access_token": "[REDACTED]"},
        "[REDACTED]",
        "safe",
    ]
