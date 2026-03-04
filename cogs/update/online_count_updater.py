# cogs/update/online_count_updater.py
"""
Cog pour mettre à jour les noms de channels vocaux avec le nombre de membres en ligne par rang.
"""

import discord
import logging
from datetime import datetime, timedelta
from discord.ext import commands, tasks

from cogs.configuration.services.role_service import RoleConfigurationService
from cogs.configuration.services.channel_service import ChannelConfigurationService

logger = logging.getLogger(__name__)

RANK_NAMES = {"fer", "bronze", "argent", "or", "platine", "diamant", "ascendant", "immortel", "radiant"}

ALPHABET_STYLE = {
    "a": "𝙖", "b": "𝙗", "c": "𝙘", "d": "𝙙", "e": "𝙚", "f": "𝙛", "g": "𝙜",
    "h": "𝙝", "i": "𝙞", "j": "𝙟", "k": "𝙠", "l": "𝙡", "m": "𝙢", "n": "𝙣",
    "o": "𝙤", "p": "𝙥", "q": "𝙦", "r": "𝙧", "s": "𝙨", "t": "𝙩", "u": "𝙪",
    "v": "𝙫", "w": "𝙬", "x": "𝙭", "y": "𝙮", "z": "𝙯",
}

DIGITS_STYLE = {
    "0": "𝟬", "1": "𝟭", "2": "𝟮", "3": "𝟯", "4": "𝟰",
    "5": "𝟱", "6": "𝟲", "7": "𝟷", "8": "𝟴", "9": "𝟵",
}


def stylize(text: str) -> str:
    """Transforme le texte en police spéciale Unicode."""
    result = ""
    for char in text:
        lower_char = char.lower()
        if lower_char in ALPHABET_STYLE:
            styled_char = ALPHABET_STYLE[lower_char]
            result += styled_char.upper() if char.isupper() else styled_char
        elif char in DIGITS_STYLE:
            result += DIGITS_STYLE[char]
        else:
            result += char
    return result


class OnlineCountUpdater(commands.Cog):
    """Met à jour les noms de channels vocaux avec le nombre de membres en ligne par rang."""

    def __init__(
        self,
        bot: commands.Bot,
        role_config_svc: RoleConfigurationService,
        channel_config_svc: ChannelConfigurationService,
    ):
        self.bot = bot
        self._role_svc = role_config_svc
        self._channel_svc = channel_config_svc
        self._edit_timestamps: dict[int, list[datetime]] = {}
        self.refresh_loop.start()

    def cog_unload(self):
        self.refresh_loop.cancel()

    async def _get_config(self, guild_id: int) -> dict:
        """Récupère la config des rôles et channels de rang."""
        roles_config = await self._role_svc.get_all(guild_id)
        channels_config = await self._channel_svc.get_all(guild_id)

        return {
            "roles": {k: v for k, v in roles_config.items() if k in RANK_NAMES},
            "channels": {k: v for k, v in channels_config.items() if k in RANK_NAMES},
        }

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        """Détecte les changements online/offline et met à jour les channels."""
        if (before.status == discord.Status.offline) != (after.status == discord.Status.offline):
            guild = after.guild
            config = await self._get_config(guild.id)
            roles_cfg = config.get("roles", {})
            if not roles_cfg:
                return

            member_role_ids = {r.id for r in after.roles}
            only_ranks = {rank for rank, role_id in roles_cfg.items() if role_id in member_role_ids}
            if only_ranks:
                await self._refresh_guild(guild, config=config, only_ranks=only_ranks)

    async def _refresh_guild(self, guild, config=None, only_ranks=None):
        """Rafraîchit les noms de channels pour un serveur."""
        if config is None:
            config = await self._get_config(guild.id)

        roles_cfg = config.get("roles", {})
        channels_cfg = config.get("channels", {})
        if not roles_cfg or not channels_cfg:
            return

        for rank, role_id in roles_cfg.items():
            if only_ranks is not None and rank not in only_ranks:
                continue

            channel_id = channels_cfg.get(rank)
            if not channel_id:
                continue

            role = guild.get_role(role_id)
            channel = guild.get_channel(channel_id)
            if not role or not channel:
                continue

            online_count = sum(1 for m in role.members if m.status != discord.Status.offline)
            new_name = f"{stylize(rank.capitalize())} - {stylize(str(online_count))} {stylize('en ligne')}"

            if channel.name != new_name:
                await self._edit_channel_name(channel, new_name)

    async def _edit_channel_name(self, channel, new_name: str):
        """Renomme un channel avec rate limiting (max 2 edits / 10 min)."""
        now = datetime.utcnow()
        timestamps = self._edit_timestamps.setdefault(channel.id, [])

        ten_min_ago = now - timedelta(minutes=10)
        timestamps = [t for t in timestamps if t > ten_min_ago]
        self._edit_timestamps[channel.id] = timestamps

        if len(timestamps) < 2:
            try:
                await channel.edit(name=new_name)
                timestamps.append(now)
            except Exception as e:
                logger.error(f"Erreur édition channel {channel.id}: {e}")

    @tasks.loop(minutes=10)
    async def refresh_loop(self):
        """Rafraîchissement périodique de tous les serveurs."""
        for guild in self.bot.guilds:
            try:
                await self._refresh_guild(guild)
            except Exception as e:
                logger.error(f"Erreur refresh guild {guild.id}: {e}")

    @refresh_loop.before_loop
    async def before_refresh_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    role_config_svc = getattr(bot, "role_config_svc", None)
    channel_config_svc = getattr(bot, "channel_config_svc", None)

    if not role_config_svc or not channel_config_svc:
        logger.error("Services config manquants. OnlineCountUpdater non chargé.")
        return

    await bot.add_cog(OnlineCountUpdater(bot, role_config_svc, channel_config_svc))
    logger.info("OnlineCountUpdater chargé.")
