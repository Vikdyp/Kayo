from __future__ import annotations

import inspect

import pytest

import bot
from config import ConfigValidationError, load_runtime_settings, validate_runtime_config
from cogs.moderation.clean import Clean
import tools.smoke_runtime as smoke_runtime


def test_build_postgres_dsn_prefers_direct_dsn(monkeypatch) -> None:
    settings = load_runtime_settings({"DATABASE_URL": "postgresql://direct"})
    monkeypatch.setattr(bot, "SETTINGS", settings)

    assert bot._build_postgres_dsn() == "postgresql://direct"


def test_build_postgres_dsn_quotes_reserved_characters(monkeypatch) -> None:
    settings = load_runtime_settings(
        {
            "DATABASE_USER": "user@example",
            "DATABASE_PASSWORD": "p@ss:word/with%",
            "DATABASE_NAME": "kayo/prod",
            "DATABASE_HOST": "localhost",
            "DATABASE_PORT": "5432",
            "DATABASE_SSL": "true",
        }
    )
    monkeypatch.setattr(bot, "SETTINGS", settings)

    assert (
        bot._build_postgres_dsn()
        == "postgresql://user%40example:p%40ss%3Aword%2Fwith%25@localhost:5432/kayo%2Fprod?sslmode=require"
    )


def test_validate_runtime_config_reports_missing_required_values() -> None:
    settings = load_runtime_settings(
        {
            "TEST_MODE": "true",
            "DATABASE_USER": "user",
            "DATABASE_PASSWORD": "password",
            "DATABASE_HOST": "localhost",
            "DATABASE_NAME": "prod",
        }
    )

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_runtime_config(settings)

    message = str(exc_info.value)
    assert "DISCORD_TOKEN_TEST" in message
    assert "TEST_GUILD_ID" in message
    assert "DATABASE_TEST_NAME" in message


def test_validate_runtime_config_accepts_direct_database_dsn() -> None:
    settings = load_runtime_settings(
        {
            "DISCORD_TOKEN": "token",
            "DATABASE_URL": "postgresql://direct",
        }
    )

    validate_runtime_config(settings)


@pytest.mark.asyncio
async def test_load_extensions_fails_when_setup_registers_no_cog(monkeypatch) -> None:
    bot_instance = bot.KayoBot()

    async def fake_load_extension(_path: str) -> None:
        return None

    async def fake_unload_extension(_path: str) -> None:
        return None

    monkeypatch.setattr(bot_instance, "load_extension", fake_load_extension)
    monkeypatch.setattr(bot_instance, "unload_extension", fake_unload_extension)

    with pytest.raises(RuntimeError, match="fake.empty"):
        await bot_instance._load_extensions(["fake.empty"])

    await bot_instance.close()


class _FakeResponse:
    def __init__(self, *, done: bool) -> None:
        self._done = done
        self.sent: list[tuple[str, bool]] = []

    def is_done(self) -> bool:
        return self._done

    async def send_message(self, message: str, *, ephemeral: bool) -> None:
        self.sent.append((message, ephemeral))
        self._done = True


class _FakeFollowup:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bool]] = []

    async def send(self, message: str, *, ephemeral: bool) -> None:
        self.sent.append((message, ephemeral))


class _FakeInteraction:
    def __init__(self, *, response_done: bool) -> None:
        self.response = _FakeResponse(done=response_done)
        self.followup = _FakeFollowup()


@pytest.mark.asyncio
async def test_clean_error_sender_uses_initial_response_before_defer() -> None:
    clean = Clean(bot=object(), clean_service=object())
    interaction = _FakeInteraction(response_done=False)

    await clean._send_ephemeral_error(interaction, "Erreur")

    assert interaction.response.sent == [("Erreur", True)]
    assert interaction.followup.sent == []


@pytest.mark.asyncio
async def test_clean_error_sender_uses_followup_after_response() -> None:
    clean = Clean(bot=object(), clean_service=object())
    interaction = _FakeInteraction(response_done=True)

    await clean._send_ephemeral_error(interaction, "Erreur")

    assert interaction.response.sent == []
    assert interaction.followup.sent == [("Erreur", True)]


def test_smoke_runtime_passes_twitch_credentials_to_container() -> None:
    source = inspect.getsource(smoke_runtime.run_smoke)

    assert "twitch_client_id=os.getenv(\"TWITCH_CLIENT_ID\", \"\")" in source
    assert "twitch_client_secret=os.getenv(\"TWITCH_CLIENT_SECRET\", \"\")" in source
