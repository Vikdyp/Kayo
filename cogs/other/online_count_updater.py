# cogs/voice_management/online_count_updater.py

import discord
import logging
from datetime import datetime, timedelta

from cogs.other.service.rank_service import RankService

logger = logging.getLogger("rank_updater")

# Dictionnaire de correspondance pour la police spéciale
ALPHABET_STYLE = {
    "a": "𝙖", "b": "𝙗", "c": "𝙘", "d": "𝙙", "e": "𝙚", "f": "𝙛", "g": "𝙜",
    "h": "𝙝", "i": "𝙞", "j": "𝙟", "k": "𝙠", "l": "𝙡", "m": "𝙢", "n": "𝙣",
    "o": "𝙤", "p": "𝙥", "q": "𝙦", "r": "𝙧", "s": "𝙨", "t": "𝙩", "u": "𝙪",
    "v": "𝙫", "w": "𝙬", "x": "𝙭", "y": "𝙮", "z": "𝙯",
}

DIGITS_STYLE = {
    "0": "𝟬", "1": "𝟭", "2": "𝟮", "3": "𝟯", "4": "𝟰",
    "5": "𝟱", "6": "𝟲", "7": "𝟷", "8": "𝟴", "9": "𝟵"
}

def stylize(text: str) -> str:
    """
    Transforme le texte en appliquant la police spéciale aux lettres et chiffres.
    Pour chaque caractère, si une correspondance est trouvée, la transformation est appliquée
    en respectant la casse pour les lettres.
    """
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


class RankUpdater:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.rank_service = RankService()
        # Pour le rate-limit : stocke pour chaque salon la liste des timestamps d'édition
        self._edit_timestamps: dict[int, list[datetime]] = {}

    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        # Ne rien faire si le status n'a pas changé offline ↔ online
        if ((before.status == discord.Status.offline and after.status != discord.Status.offline)
            or (before.status != discord.Status.offline and after.status == discord.Status.offline)):

            guild = after.guild
            guild_id = guild.id
            guild_name = guild.name

            # Récupère la config mise à jour
            config = await self.rank_service.get_config(guild_id, guild_name)
            roles_cfg = config.get("roles", {})
            channels_cfg = config.get("channels", {})

            # Pour chaque rang configuré, vérifier si l'utilisateur a ce rôle
            for rank, role_id in roles_cfg.items():
                if role_id not in [r.id for r in after.roles]:
                    continue

                channel_id = channels_cfg.get(rank)
                if not channel_id:
                    continue

                role = guild.get_role(role_id)
                channel = guild.get_channel(channel_id)
                if not role or not channel:
                    continue

                # Compte les membres en ligne pour ce rôle
                online_count = sum(1 for m in role.members if m.status != discord.Status.offline)
                new_name = f"{stylize(rank.capitalize())} - {stylize(str(online_count))} {stylize('en ligne')}"

                if channel.name != new_name:
                    await self._edit_channel_name(channel, new_name)

    async def _edit_channel_name(self, channel: discord.TextChannel, new_name: str):
        """Nomme le salon en limitant à 2 edits toutes les 10 minutes par salon."""
        now = datetime.utcnow()
        timestamps = self._edit_timestamps.setdefault(channel.id, [])

        # Conserve uniquement les timestamps des 10 dernières minutes
        ten_min_ago = now - timedelta(minutes=10)
        timestamps = [t for t in timestamps if t > ten_min_ago]
        self._edit_timestamps[channel.id] = timestamps

        if len(timestamps) < 2:
            try:
                await channel.edit(name=new_name)
                timestamps.append(now)
                logger.info(f"Salon {channel.id} renommé en « {new_name} »")
            except Exception as e:
                logger.error(f"Erreur lors de l'édition du salon {channel.id} : {e}")
        else:
            logger.warning(f"Rate limit atteint pour le salon {channel.id} — update ignorée.")

    def start(self):
        """Active le RankUpdater (listener de présence)."""
        logger.info("RankUpdater : écoute des mises à jour de présence activée.")

    def stop(self):
        """Désactive le RankUpdater."""
        logger.info("RankUpdater : écoute des mises à jour de présence désactivée.")


# Singleton
rank_updater = RankUpdater(None)


def setup_rank_updater(bot: discord.Client):
    """Initialise et configure le RankUpdater avec le bot."""
    rank_updater.bot = bot
    rank_updater.rank_service = RankService()
    # Écoute les mises à jour de présence
    bot.add_listener(rank_updater.on_presence_update, 'on_presence_update')
    rank_updater.start()
    logger.info("RankUpdater setup complete.")


def teardown_rank_updater():
    """Arrête le RankUpdater."""
    rank_updater.stop()
    logger.info("RankUpdater teardown complete.")
