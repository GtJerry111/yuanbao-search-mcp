from yuanbao_search_mcp.config import Settings, load_settings


def test_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.transport == "stdio"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8765
    assert settings.weixin_default_limit == 20
    assert settings.weixin_max_results == 28
    assert settings.academic_summary_default is False
    assert settings.academic_summary_timeout == 45.0
    assert settings.enable_weixin_search is True


def test_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("YUANBAO_TRANSPORT", "streamable-http")
    monkeypatch.setenv("YUANBAO_PORT", "9999")
    monkeypatch.setenv("YUANBAO_ACADEMIC_SUMMARY_DEFAULT", "true")
    monkeypatch.setenv("YUANBAO_ENABLE_WEB_SEARCH", "false")
    settings = Settings(_env_file=None)
    assert settings.transport == "streamable-http"
    assert settings.port == 9999
    assert settings.academic_summary_default is True
    assert settings.enable_web_search is False


def test_cli_overrides_env(monkeypatch) -> None:
    monkeypatch.setenv("YUANBAO_PORT", "9999")
    settings = load_settings(["--port", "8765", "--transport", "stdio"])
    assert settings.port == 8765
    assert settings.transport == "stdio"


def test_invalid_port_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        Settings(_env_file=None, port=70000)


def test_cli_invalid_port_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        load_settings(["--port", "70000"])


def test_cli_invalid_log_level_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        load_settings(["--log-level", "bogus"])
