# cogs/update/rank_up.py
"""
Cog de suivi des changements de rang Valorant - UI Discord uniquement.
"""

import discord
from discord.ext import commands
import asyncio
import time
import logging

from cogs.configuration.services.role_service import RoleConfigurationService
from cogs.configuration.services.channel_service import ChannelConfigurationService

logger = logging.getLogger(__name__)

# Ordre des rangs (1 = meilleur, 9 = moins bon)
RANK_ORDER = {
    "radiant": 1,
    "immortel": 2,
    "ascendant": 3,
    "diamant": 4,
    "platine": 5,
    "or": 6,
    "argent": 7,
    "bronze": 8,
    "fer": 9,
}

RANK_NAMES = set(RANK_ORDER.keys())


class RoleChangeCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        role_config_svc: RoleConfigurationService,
        channel_config_svc: ChannelConfigurationService,
    ):
        self.bot = bot
        self._role_svc = role_config_svc
        self._channel_svc = channel_config_svc

        # Cache pour la config (évite les appels DB à chaque événement)
        self._config_cache = {}
        self._cache_ttl = 300  # 5 minutes

        # Pending removal pour détecter les transitions de rang
        self.pending_removal = {}

    async def _get_config(self, guild: discord.Guild) -> dict:
        """Récupère la config depuis le cache ou la base de données."""
        now = time.time()
        cached = self._config_cache.get(guild.id)

        if cached and cached["expires"] > now:
            return cached

        roles_config = await self._role_svc.get_all(guild.id)
        log_channel_id = await self._channel_svc.get_one(guild.id, "rank_up")

        rank_roles = {k: v for k, v in roles_config.items() if k in RANK_NAMES}

        config = {
            "roles": rank_roles,
            "log_channel_id": log_channel_id,
            "expires": now + self._cache_ttl,
        }
        self._config_cache[guild.id] = config
        return config

    async def _get_log_channel(self, guild: discord.Guild):
        config = await self._get_config(guild)
        channel_id = config.get("log_channel_id")
        if not channel_id:
            return None
        return self.bot.get_channel(channel_id)

    def _get_rank_role_ids(self, config: dict) -> set[int]:
        return set(config.get("roles", {}).values())

    def _get_rank_name_by_id(self, config: dict, role_id: int):
        for name, rid in config.get("roles", {}).items():
            if rid == role_id:
                return name
        return None

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        config = await self._get_config(after.guild)
        rank_role_ids = self._get_rank_role_ids(config)

        if not rank_role_ids:
            return

        old_rank_ids = {r.id for r in before.roles if r.id in rank_role_ids}
        new_rank_ids = {r.id for r in after.roles if r.id in rank_role_ids}

        removed_ids = old_rank_ids - new_rank_ids
        added_ids = new_rank_ids - old_rank_ids

        removed = {self._get_rank_name_by_id(config, rid) for rid in removed_ids}
        added = {self._get_rank_name_by_id(config, rid) for rid in added_ids}
        removed.discard(None)
        added.discard(None)

        key = (after.guild.id, after.id)

        if removed:
            self.pending_removal[key] = {
                "removed": removed,
                "timestamp": time.time(),
            }
            asyncio.create_task(self._finalize_removal(after, config))

        if added:
            if key in self.pending_removal:
                data = self.pending_removal[key]
                old_removed = data["removed"]

                if len(old_removed) == 1 and len(added) == 1:
                    old_rank = list(old_removed)[0]
                    new_rank = list(added)[0]
                    del self.pending_removal[key]

                    await self._send_rank_change_message(
                        member=after,
                        old_rank=old_rank,
                        new_rank=new_rank,
                        config=config,
                    )
                    return

    async def _finalize_removal(
        self, member: discord.Member, config: dict, delay: float = 2.0
    ):
        await asyncio.sleep(delay)
        key = (member.guild.id, member.id)
        if key in self.pending_removal:
            data = self.pending_removal[key]
            if time.time() - data["timestamp"] >= delay:
                del self.pending_removal[key]

    async def _send_rank_change_message(
        self,
        member: discord.Member,
        old_rank: str,
        new_rank: str,
        config: dict,
    ):
        log_channel = await self._get_log_channel(member.guild)
        if not log_channel:
            return

        old_val = RANK_ORDER.get(old_rank, 99)
        new_val = RANK_ORDER.get(new_rank, 99)

        # Calcul du percentile
        rank_role_ids = self._get_rank_role_ids(config)
        total_ranked = 0
        worse_count = 0

        for m in member.guild.members:
            member_rank_ids = [r.id for r in m.roles if r.id in rank_role_ids]
            if not member_rank_ids:
                continue

            total_ranked += 1
            member_rank_values = []
            for rid in member_rank_ids:
                rank_name = self._get_rank_name_by_id(config, rid)
                if rank_name:
                    member_rank_values.append(RANK_ORDER.get(rank_name, 99))

            if member_rank_values:
                best_rank = min(member_rank_values)
                if best_rank > new_val:
                    worse_count += 1

        if total_ranked > 0:
            top_percentile = 100 - (worse_count / total_ranked) * 100
        else:
            top_percentile = 100

        if top_percentile < 1:
            top_percentile_str = f"{top_percentile:.2f}".replace(".", ",")
        else:
            top_percentile_str = f"{top_percentile:.0f}"

        stat_msg = f" Tu fais partie du top {top_percentile_str}% des membres !"

        emoji_obj = discord.utils.get(member.guild.emojis, name=new_rank)
        emoji = str(emoji_obj) if emoji_obj else ""

        if new_val < old_val:
            msg = f"{member.mention} vient de passer **{new_rank.capitalize()}** {emoji}.{stat_msg}"
        else:
            msg = f"{member.mention} a derank **{new_rank.capitalize()}** {emoji}. Force à toi !"

        await log_channel.send(msg)


async def setup(bot: commands.Bot):
    role_config_svc = getattr(bot, "role_config_svc", None)
    channel_config_svc = getattr(bot, "channel_config_svc", None)

    if not role_config_svc or not channel_config_svc:
        logger.error("Services config manquants. RoleChangeCog non chargé.")
        return

    await bot.add_cog(RoleChangeCog(bot, role_config_svc, channel_config_svc))
    logger.info("RoleChangeCog chargé.")
