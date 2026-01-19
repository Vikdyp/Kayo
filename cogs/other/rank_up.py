import discord
from discord.ext import commands
import asyncio
import time
import logging

from cogs.configuration.services.role_service import ServerRoleService
from cogs.configuration.services.channel_service import ServerChannelService

logger = logging.getLogger('cogs.rank_up')

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
    "fer": 9
}

RANK_NAMES = set(RANK_ORDER.keys())


class RoleChangeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Cache pour la config (évite les appels DB à chaque événement)
        # Structure: {guild_id: {"roles": {}, "log_channel_id": int, "expires": timestamp}}
        self._config_cache = {}
        self._cache_ttl = 300  # 5 minutes

        # Mémorise temporairement les rôles retirés en attendant
        # de voir si un nouveau rôle arrive pour ce membre
        # Structure : pending_removal[(guild_id, user_id)] = {
        #    "removed": set(["or", "argent", ...]),
        #    "timestamp": time.time()
        # }
        self.pending_removal = {}

    async def _get_config(self, guild: discord.Guild) -> dict:
        """Récupère la config depuis le cache ou la base de données."""
        now = time.time()
        cached = self._config_cache.get(guild.id)

        if cached and cached["expires"] > now:
            return cached

        # Récupérer depuis la DB
        roles_config = await ServerRoleService.get_roles_config(guild.id, guild.name)
        log_channel_id = await ServerChannelService.get_channel_id(guild.id, guild.name, "rank_up")

        # Filtrer uniquement les rôles de rang
        rank_roles = {k: v for k, v in roles_config.items() if k in RANK_NAMES}

        config = {
            "roles": rank_roles,
            "log_channel_id": log_channel_id,
            "expires": now + self._cache_ttl
        }
        self._config_cache[guild.id] = config
        return config

    async def _get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """Récupère le channel de log depuis la config."""
        config = await self._get_config(guild)
        channel_id = config.get("log_channel_id")
        if not channel_id:
            return None
        return self.bot.get_channel(channel_id)

    def _get_rank_role_ids(self, config: dict) -> set[int]:
        """Retourne les IDs des rôles de rang configurés."""
        return set(config.get("roles", {}).values())

    def _get_rank_name_by_id(self, config: dict, role_id: int) -> str | None:
        """Retourne le nom du rang à partir de l'ID du rôle."""
        for name, rid in config.get("roles", {}).items():
            if rid == role_id:
                return name
        return None

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        config = await self._get_config(after.guild)
        rank_role_ids = self._get_rank_role_ids(config)

        if not rank_role_ids:
            return  # Pas de config pour ce serveur

        # Identifier les rôles de rang avant/après
        old_rank_ids = {r.id for r in before.roles if r.id in rank_role_ids}
        new_rank_ids = {r.id for r in after.roles if r.id in rank_role_ids}

        # Rôles supprimés / ajoutés
        removed_ids = old_rank_ids - new_rank_ids
        added_ids = new_rank_ids - old_rank_ids

        # Convertir en noms de rang
        removed = {self._get_rank_name_by_id(config, rid) for rid in removed_ids}
        added = {self._get_rank_name_by_id(config, rid) for rid in added_ids}
        removed.discard(None)
        added.discard(None)

        key = (after.guild.id, after.id)

        # Cas 1 : retrait de rôle(s)
        if removed:
            self.pending_removal[key] = {
                "removed": removed,
                "timestamp": time.time()
            }
            asyncio.create_task(self._finalize_removal(after, config))

        # Cas 2 : ajout de rôle(s)
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
                        config=config
                    )
                    return

    async def _finalize_removal(self, member: discord.Member, config: dict, delay: float = 2.0):
        """Attend quelques secondes pour voir si un nouveau rôle arrive."""
        await asyncio.sleep(delay)

        key = (member.guild.id, member.id)
        if key in self.pending_removal:
            data = self.pending_removal[key]
            if time.time() - data["timestamp"] >= delay:
                del self.pending_removal[key]
                # Le membre a juste perdu son rang sans en recevoir un nouveau
                # (pas de message envoyé par défaut)

    async def _send_rank_change_message(
        self,
        member: discord.Member,
        old_rank: str,
        new_rank: str,
        config: dict
    ):
        """Envoie un message de promotion/rétrogradation avec la stat de position."""
        log_channel = await self._get_log_channel(member.guild)
        if not log_channel:
            logger.warning(f"[RoleChangeCog] Pas de channel rank_up configuré pour {member.guild.name}")
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
            # Trouver le meilleur rang du membre
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

        # Formatage du pourcentage
        if top_percentile < 1:
            top_percentile_str = f"{top_percentile:.2f}".replace('.', ',')
        else:
            top_percentile_str = f"{top_percentile:.0f}"

        stat_msg = f" Tu fais partie du top {top_percentile_str}% des membres !"

        # Emoji personnalisé
        emoji_obj = discord.utils.get(member.guild.emojis, name=new_rank)
        emoji = str(emoji_obj) if emoji_obj else ""

        if new_val < old_val:
            # Promotion
            msg = f"{member.mention} vient de passer **{new_rank.capitalize()}** {emoji}.{stat_msg}"
        else:
            # Rétrogradation
            msg = f"{member.mention} a derank **{new_rank.capitalize()}** {emoji}. Force à toi !"

        await log_channel.send(msg)


async def setup(bot):
    await bot.add_cog(RoleChangeCog(bot))
