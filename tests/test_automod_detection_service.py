from types import SimpleNamespace

from cogs.moderation.services.automod_detection_service import AutomodDetectionService


def _member(
    *,
    bot: bool = False,
    administrator: bool = False,
    manage_messages: bool = False,
    ban_members: bool = False,
    roles: list[int] | None = None,
):
    return SimpleNamespace(
        bot=bot,
        guild_permissions=SimpleNamespace(
            administrator=administrator,
            manage_messages=manage_messages,
            ban_members=ban_members,
        ),
        roles=[SimpleNamespace(id=role_id) for role_id in (roles or [])],
    )


def test_detects_builtin_scam_patterns() -> None:
    service = AutomodDetectionService()

    assert service.is_scam_content("Claim your free nitro now", {}) is True
    assert service.is_scam_content("message normal", {}) is False


def test_detects_builtin_and_custom_scam_domains() -> None:
    service = AutomodDetectionService()
    config = {"custom_scam_domains": ["BadDomain.Example"]}

    assert service.is_scam_domain("https://cdn.discordgift.site/path", {}) is True
    assert service.is_scam_domain("https://login.baddomain.example/path", config) is True
    assert service.is_scam_domain("https://discord.com/channels/1/2", config) is False


def test_detects_custom_scam_patterns_and_ignores_invalid_regex() -> None:
    service = AutomodDetectionService()
    config = {"custom_scam_patterns": ["[", r"kayo-special-\d+"]}

    assert service.is_scam_content("kayo-special-42", config) is True
    assert service.is_scam_content("kayo-special", config) is False


def test_scam_message_content_checks_urls_and_text() -> None:
    service = AutomodDetectionService()

    assert service.is_scam_message_content("see https://discord-nitro.gift/free", {}) is True
    assert service.is_scam_message_content("just a normal https://discord.com url", {}) is False


def test_whitelist_checks_member_permissions_roles_and_channels() -> None:
    service = AutomodDetectionService()
    config = {
        "whitelisted_roles": [42],
        "whitelisted_channels": [123],
    }

    assert service.is_member_whitelisted(_member(bot=True), config) is True
    assert service.is_member_whitelisted(_member(administrator=True), config) is True
    assert service.is_member_whitelisted(_member(manage_messages=True), config) is True
    assert service.is_member_whitelisted(_member(ban_members=True), config) is True
    assert service.is_member_whitelisted(_member(roles=[42]), config) is True
    assert service.is_member_whitelisted(_member(roles=[99]), config) is False
    assert service.is_channel_whitelisted(123, config) is True
    assert service.is_channel_whitelisted(456, config) is False
