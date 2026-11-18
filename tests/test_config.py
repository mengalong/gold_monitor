import config


def test_default_settings_are_valid():
    assert config.validate_settings() == []


def test_invalid_timezone_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "TIMEZONE", "Invalid/Timezone")

    errors = config.validate_settings()

    assert len(errors) == 1
    assert "APP_TIMEZONE" in errors[0]


def test_placeholder_fred_key_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "FRED_API_KEY", "your-key")

    errors = config.validate_settings()

    assert len(errors) == 1
    assert "FRED_API_KEY" in errors[0]
