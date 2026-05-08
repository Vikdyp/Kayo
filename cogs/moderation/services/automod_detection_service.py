# cogs/moderation/services/automod_detection_service.py
"""Pure detection helpers for the AutoMod cog."""

from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import urlparse

import discord


SCAM_PATTERNS = [
    r"free\s*nitro",
    r"discord\s*nitro\s*(for\s*)?free",
    r"steam\s*gift",
    r"@everyone.*free",
    r"claim\s*your\s*(free\s*)?gift",
    r"airdrop",
    r"free\s*discord\s*nitro",
    r"nitro\s*gratuit",
    r"get\s*free\s*nitro",
    r"discord\.gift",
    r"steamcommunity\.com.*gift",
]

SCAM_DOMAINS = [
    "discordgift.site",
    "discord-nitro.gift",
    "discordnitro.gift",
    "steamcommunity.ru",
    "steampowered.ru",
    "dicsord.gift",
    "discorrd.gift",
    "dlscord.gift",
    "disc0rd.gift",
    "discordapp.gift",
    "discord-app.gift",
    "discordgiveaway.com",
    "free-nitro.com",
    "nitro-discord.com",
    "steamgifts.ru",
]

URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')


class AutomodDetectionService:
    """Side-effect-free detection logic used by AutoMod."""

    def __init__(
        self,
        scam_patterns: Iterable[str] = SCAM_PATTERNS,
        scam_domains: Iterable[str] = SCAM_DOMAINS,
    ) -> None:
        self.scam_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in scam_patterns
        ]
        self.scam_domains = tuple(domain.lower() for domain in scam_domains)

    def is_member_whitelisted(
        self,
        member: discord.Member,
        config: dict[str, Any],
    ) -> bool:
        if member.bot:
            return True
        if member.guild_permissions.administrator:
            return True
        if member.guild_permissions.manage_messages:
            return True
        if member.guild_permissions.ban_members:
            return True

        whitelisted_roles = config.get("whitelisted_roles", []) or []
        member_role_ids = [role.id for role in member.roles]
        return any(role_id in member_role_ids for role_id in whitelisted_roles)

    def is_channel_whitelisted(self, channel_id: int, config: dict[str, Any]) -> bool:
        whitelisted_channels = config.get("whitelisted_channels", []) or []
        return channel_id in whitelisted_channels

    def extract_urls(self, content: str) -> list[str]:
        return URL_PATTERN.findall(content)

    def is_scam_domain(self, url: str, config: dict[str, Any]) -> bool:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            for scam_domain in self.scam_domains:
                if domain == scam_domain or domain.endswith("." + scam_domain):
                    return True

            custom_domains = config.get("custom_scam_domains", []) or []
            for scam_domain in custom_domains:
                normalized_domain = str(scam_domain).lower()
                if domain == normalized_domain or domain.endswith("." + normalized_domain):
                    return True

        except Exception:
            pass
        return False

    def is_scam_content(self, content: str, config: dict[str, Any]) -> bool:
        content_lower = content.lower()

        for pattern in self.scam_patterns:
            if pattern.search(content_lower):
                return True

        custom_patterns = config.get("custom_scam_patterns", []) or []
        for pattern_str in custom_patterns:
            try:
                pattern = re.compile(pattern_str, re.IGNORECASE)
                if pattern.search(content_lower):
                    return True
            except re.error:
                continue

        return False

    def is_scam_message_content(self, content: str, config: dict[str, Any]) -> bool:
        if self.is_scam_content(content, config):
            return True

        for url in self.extract_urls(content):
            if self.is_scam_domain(url, config):
                return True

        return False
