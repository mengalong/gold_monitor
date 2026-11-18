from security import redact_secrets


def test_known_secret_is_redacted():
    assert redact_secrets("request failed: known-secret", ("known-secret",)) == "request failed: ***"


def test_sensitive_query_parameters_are_redacted():
    message = "https://example.test/data?api_key=fake-key&token=fake-token&series=gold"

    result = redact_secrets(message)

    assert "fake-key" not in result
    assert "fake-token" not in result
    assert "api_key=***" in result
    assert "token=***" in result


def test_regular_query_parameters_are_preserved():
    message = "https://example.test/data?series_id=DFII10&limit=10"

    assert redact_secrets(message) == message
