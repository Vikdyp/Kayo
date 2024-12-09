import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from cogs.utilities.data_manager import DataManager

logger = logging.getLogger('discord.voice_management.five_stack')

VALID_RANKS = ["Fer", "Bronze", "Argent", "Or", "Platine", "Diamant", "Ascendant", "Immortel", "Radiant"]
VALID_AGENT_ROLES = ["sentinel", "duelist", "controller", "initiator", "fill"]
CATEGORY_ID = 1315786915005599824  # ID de la catégorie où créer les salons

class FiveStack(commands.Cog):
    """Cog pour la commande de création de salons vocaux basés sur le rang et le rôle agent."""
    dependencies = ["cogs.voice_management.cleanup"]

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.config: Dict[str, Any] = {}
        self.tracked_channels: Dict[int, Dict[str, Any]] = {}
        # tracked_channels[voice_channel_id] = {
        #   "rank": rank_name,
        #   "players": [(user_id, agent_role), ...],
        #   "voice_channel": voice_channel,
        #   "last_active": datetime
        # }
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        self.config = await self.data.get_config()
        logger.info("FiveStack: Configuration chargée avec succès.")

    def get_user_rank(self, member: discord.Member) -> Optional[str]:
        for role in member.roles:
            if role.name in VALID_RANKS:
                return role.name
        return None

    def get_user_agent_role(self, member: discord.Member) -> Optional[str]:
        for role in member.roles:
            if role.name.lower() in VALID_AGENT_ROLES:
                return role.name.lower()
        return None

    def rank_difference_ok(self, base_rank: str, user_rank: str) -> bool:
        try:
            base_i = VALID_RANKS.index(base_rank)
            user_i = VALID_RANKS.index(user_rank)
            return abs(base_i - user_i) <= 1
        except ValueError:
            return False

    def can_join_channel(self, channel_info: Dict[str, Any], agent_role: str) -> bool:
        players = channel_info["players"]
        if len(players) >= 5:
            return False

        count_sentinel = sum(1 for p in players if p[1] == "sentinel")
        count_duelist = sum(1 for p in players if p[1] == "duelist")
        count_controller = sum(1 for p in players if p[1] == "controller")
        count_initiator = sum(1 for p in players if p[1] == "initiator")
        count_fill = sum(1 for p in players if p[1] == "fill")

        if agent_role != "fill":
            if agent_role == "sentinel" and count_sentinel >= 1:
                return False
            if agent_role == "duelist" and count_duelist >= 1:
                return False
            if agent_role == "controller" and count_controller >= 1:
                return False
            if agent_role == "initiator" and count_initiator >= 1:
                return False
            return True
        else:
            # fill
            if count_fill >= 2:
                return False
            return True

    def add_player_to_channel_info(self, channel_info: Dict[str, Any], user_id: int, agent_role: str):
        channel_info["players"].append((user_id, agent_role))
        channel_info["last_active"] = datetime.now(timezone.utc)

    def find_suitable_channel(self, user_rank: str, agent_role: str) -> Optional[int]:
        for vc_id, info in self.tracked_channels.items():
            if info["rank"] == user_rank:
                if self.can_join_channel(info, agent_role):
                    return vc_id
        return None

    async def create_channel(self, guild: discord.Guild, rank: str) -> discord.VoiceChannel:
        category = guild.get_channel(CATEGORY_ID)
        if not category or category.type != discord.ChannelType.category:
            raise ValueError("Catégorie invalide ou introuvable.")
        voice_channel_name = f"{rank} Team Channel"
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=False)
        }
        voice_channel = await guild.create_voice_channel(
            voice_channel_name,
            category=category,
            user_limit=5,
            overwrites=overwrites
        )
        return voice_channel

    async def give_access_to_user(self, voice_channel: discord.VoiceChannel, member: discord.Member):
        # Donner accès à un utilisateur (connect, view_channel)
        perms = voice_channel.overwrites_for(member)
        perms.connect = True
        perms.view_channel = True
        await voice_channel.set_permissions(member, overwrite=perms)

    @app_commands.command(name="five_stack", description="Trouver ou créer un salon pour une équipe de 5 en fonction du rang et du rôle agent.")
    async def five_stack(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_rank = self.get_user_rank(interaction.user)
        if not user_rank:
            return await interaction.followup.send("Vous n'avez pas de rôle de rang valide.", ephemeral=True)

        agent_role = self.get_user_agent_role(interaction.user)
        if not agent_role:
            return await interaction.followup.send("Vous n'avez pas de rôle agent valide (sentinel/duelist/controller/initiator/fill).", ephemeral=True)

        suitable_channel_id = self.find_suitable_channel(user_rank, agent_role)
        if suitable_channel_id is not None:
            voice_channel = self.tracked_channels[suitable_channel_id]["voice_channel"]
            if self.can_join_channel(self.tracked_channels[suitable_channel_id], agent_role):
                self.add_player_to_channel_info(self.tracked_channels[suitable_channel_id], interaction.user.id, agent_role)
                await self.give_access_to_user(voice_channel, interaction.user)
                if interaction.user.voice:
                    try:
                        await interaction.user.move_to(voice_channel)
                        await interaction.followup.send(f"Vous avez été ajouté au salon {voice_channel.mention}.", ephemeral=True)
                    except:
                        await interaction.followup.send(f"Rejoignez le salon manuellement : {voice_channel.mention}", ephemeral=True)
                else:
                    await interaction.followup.send(f"Vous avez été ajouté à l'équipe. Rejoignez le salon : {voice_channel.mention}", ephemeral=True)
            else:
                await interaction.followup.send("Aucun salon approprié n'est disponible.", ephemeral=True)
        else:
            # Créer un nouveau salon
            try:
                voice_channel = await self.create_channel(interaction.guild, user_rank)
                vc_id = voice_channel.id
                self.tracked_channels[vc_id] = {
                    "rank": user_rank,
                    "players": [],
                    "voice_channel": voice_channel,
                    "last_active": datetime.now(timezone.utc)
                }

                if self.can_join_channel(self.tracked_channels[vc_id], agent_role):
                    self.add_player_to_channel_info(self.tracked_channels[vc_id], interaction.user.id, agent_role)
                    await self.give_access_to_user(voice_channel, interaction.user)
                    if interaction.user.voice:
                        try:
                            await interaction.user.move_to(voice_channel)
                            await interaction.followup.send(f"Salon créé : {voice_channel.mention} et vous y avez été déplacé.", ephemeral=True)
                        except:
                            await interaction.followup.send(f"Salon créé : {voice_channel.mention}. Rejoignez-le manuellement.", ephemeral=True)
                    else:
                        await interaction.followup.send(f"Salon créé : {voice_channel.mention}, rejoignez-le manuellement.", ephemeral=True)
                else:
                    # Personne ne peut y rentrer (rare), on laisse vide ou on peut supprimer
                    await interaction.followup.send("Aucun slot disponible, salon inutilisable. (Cas rare)", ephemeral=True)
            except Exception as e:
                logger.exception(f"Erreur lors de la création du salon: {e}")
                await interaction.followup.send("Erreur lors de la création du salon vocal.", ephemeral=True)

    @app_commands.command(name="five_stack_invite", description="Inviter un utilisateur dans un salon existant.")
    @app_commands.describe(user="Utilisateur à inviter", channel_id="ID du salon vocal")
    async def five_stack_invite(self, interaction: discord.Interaction, user: discord.Member, channel_id: int):
        await interaction.response.defer(ephemeral=True)
        if channel_id not in self.tracked_channels:
            return await interaction.followup.send("Salon non suivi ou introuvable.", ephemeral=True)

        channel_info = self.tracked_channels[channel_id]
        voice_channel = channel_info["voice_channel"]
        # Vérifier le rang du user
        user_rank = self.get_user_rank(user)
        if not user_rank:
            return await interaction.followup.send(f"{user.mention} n'a pas de rang valide.", ephemeral=True)
        # Vérifier différence de rang
        if not self.rank_difference_ok(channel_info["rank"], user_rank):
            return await interaction.followup.send(f"{user.mention} n'a pas un rang compatible (+/-1).", ephemeral=True)

        # Vérifier agent role du user
        agent_role = self.get_user_agent_role(user)
        if not agent_role:
            return await interaction.followup.send(f"{user.mention} n'a pas de rôle agent valide.", ephemeral=True)

        if self.can_join_channel(channel_info, agent_role):
            self.add_player_to_channel_info(channel_info, user.id, agent_role)
            await self.give_access_to_user(voice_channel, user)
            await interaction.followup.send(f"{user.mention} peut maintenant rejoindre : {voice_channel.mention}", ephemeral=True)
        else:
            await interaction.followup.send(f"{user.mention} ne peut pas rejoindre (composition complète ou invalide).", ephemeral=True)

    @app_commands.command(name="five_stack_create", description="Créer un salon en précisant le rang et des joueurs à ajouter.")
    @app_commands.describe(rank="Rang du vocal", user1="Joueur 1", user2="Joueur 2", user3="Joueur 3", user4="Joueur 4", user5="Joueur 5")
    async def five_stack_create(
        self,
        interaction: discord.Interaction,
        rank: str,
        user1: discord.Member,
        user2: Optional[discord.Member] = None,
        user3: Optional[discord.Member] = None,
        user4: Optional[discord.Member] = None,
        user5: Optional[discord.Member] = None
    ):
        await interaction.response.defer(ephemeral=True)
        rank = rank.capitalize()
        if rank not in VALID_RANKS:
            return await interaction.followup.send("Rang invalide.", ephemeral=True)

        # Liste des joueurs
        players = [u for u in [user1, user2, user3, user4, user5] if u is not None]

        # Créer le salon
        try:
            voice_channel = await self.create_channel(interaction.guild, rank)
        except Exception as e:
            logger.exception(f"Erreur lors de la création du salon: {e}")
            return await interaction.followup.send("Erreur lors de la création du salon vocal.", ephemeral=True)

        vc_id = voice_channel.id
        self.tracked_channels[vc_id] = {
            "rank": rank,
            "players": [],
            "voice_channel": voice_channel,
            "last_active": datetime.now(timezone.utc)
        }

        # Tenter d'ajouter chaque joueur
        added_any = False
        for member in players:
            user_rank = self.get_user_rank(member)
            if not user_rank or not self.rank_difference_ok(rank, user_rank):
                continue
            agent_role = self.get_user_agent_role(member)
            if not agent_role:
                continue
            if self.can_join_channel(self.tracked_channels[vc_id], agent_role):
                self.add_player_to_channel_info(self.tracked_channels[vc_id], member.id, agent_role)
                await self.give_access_to_user(voice_channel, member)
                added_any = True

        if not added_any:
            # Personne ajouté
            await voice_channel.delete()
            return await interaction.followup.send("Aucun joueur valide ajouté. Salon non créé.", ephemeral=True)

        # Salon créé et au moins un joueur ajouté
        await interaction.followup.send(f"Salon créé: {voice_channel.mention}. Les joueurs valides ont été ajoutés et peuvent le rejoindre.", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FiveStack(bot))
    logger.info("FiveStack Cog chargé avec succès.")
