import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
import random
import string
from typing import Optional, Dict, List, Any
import datetime
import asyncio

from .services.five_stack_service import MatchmakingService

# Constantes
FORUM_CHANNEL_ID: int = 1325629700248178778  # ID réel de votre forum
VOICE_CATEGORY_NAME: str = "Matchmaking"       # Nom de la catégorie vocale
TEAM_CODE_LENGTH: int = 6                      # Longueur du code d'équipe

logger = logging.getLogger(__name__)


def generate_team_code(length: int = TEAM_CODE_LENGTH) -> str:
    """Génère un code d'équipe aléatoire en majuscules et chiffres."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


async def get_forum_channel(bot: commands.Bot) -> Optional[discord.ForumChannel]:
    """Récupère et vérifie le ForumChannel à partir de FORUM_CHANNEL_ID."""
    channel = bot.get_channel(FORUM_CHANNEL_ID)
    if channel and isinstance(channel, discord.ForumChannel):
        return channel
    logger.error("Forum channel invalide ou introuvable.")
    return None


async def get_voice_category(guild: discord.Guild) -> Optional[discord.CategoryChannel]:
    """Récupère la catégorie vocale par son nom, ou la crée si elle n'existe pas."""
    category = discord.utils.get(guild.categories, name=VOICE_CATEGORY_NAME)
    if not category:
        try:
            category = await guild.create_category(VOICE_CATEGORY_NAME)
            logger.info(f"Catégorie '{VOICE_CATEGORY_NAME}' créée.")
        except Exception as e:
            logger.error(f"Erreur création catégorie '{VOICE_CATEGORY_NAME}': {e}")
            return None
    return category


class TeamManager(commands.Cog):
    """
    Gère la création d'équipe via /create_team, /join_team,
    l'expulsion via /kick_member, et la suppression avec /delete_team.

    Chaque équipe dispose d'un code unique et est gérée via la table 'teams'
    et 'team_members'. Dès que l'équipe atteint 5 membres, un salon vocal est créé.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.team_locks: Dict[str, asyncio.Lock] = {}
        self.bot.loop.create_task(self.initialize())
        self.cleanup_teams_task.start()

    def cog_unload(self) -> None:
        self.cleanup_teams_task.cancel()

    # ------------------------------------------------
    # Initialisation du Cog
    # ------------------------------------------------

    async def initialize(self) -> None:
        """
        Au démarrage, charge et supprime toutes les équipes existantes
        (threads/forums + vocal + BD) afin de repartir sur une base propre.
        """
        await self.load_existing_teams()
        await self.delete_all_teams()
        logger.info("Initialisation du TeamManager terminée.")

    async def load_existing_teams(self) -> None:
        """
        Charge toutes les équipes existantes pour log/debug.
        """
        try:
            teams = await MatchmakingService.get_all_teams()
            for t in teams:
                logger.info(f"Équipe existante chargée (BD): code={t['code']}")
            logger.info("Toutes les équipes existantes ont été chargées (log uniquement).")
        except Exception as e:
            logger.error(f"Erreur lors du chargement des équipes existantes : {e}")

    async def delete_all_teams(self) -> None:
        """
        Supprime toutes les équipes existantes, leurs ressources Discord et leurs enregistrements en BD.
        """
        logger.info("Début de la suppression de toutes les équipes existantes (init).")
        try:
            teams = await MatchmakingService.get_all_teams()
            for t in teams:
                code = t["code"]
                logger.info(f"Suppression de l'équipe : {code}")
                await self.delete_team_resources(t)
                success = await MatchmakingService.delete_team(code)
                if success:
                    logger.info(f"Équipe '{code}' supprimée en BD au démarrage.")
                else:
                    logger.warning(f"Impossible de supprimer l'équipe '{code}' en BD.")
        except Exception as e:
            logger.error(f"Erreur lors de la suppression des équipes : {e}")

    # ------------------------------------------------
    # Commandes
    # ------------------------------------------------

    @app_commands.command(name="create_team", description="Créer une équipe (même région que le leader).")
    @app_commands.describe(visibility="Définissez la visibilité de l'équipe.")
    @app_commands.choices(visibility=[
        app_commands.Choice(name="Public", value="public"),
        app_commands.Choice(name="Privé",  value="private")
    ])
    async def create_team(self, interaction: discord.Interaction, visibility: app_commands.Choice[str]) -> None:
        """
        Crée une équipe et un thread dans le forum. Si l'équipe est publique, un code secret est généré.
        """
        await interaction.response.defer(ephemeral=True)
        leader: discord.Member = interaction.user

        if await MatchmakingService.is_user_in_any_team(leader.id):
            await interaction.edit_original_response(content="Vous êtes déjà membre d'une équipe.")
            return

        leader_info = await MatchmakingService.get_user_info(leader.id)
        if not leader_info:
            await interaction.edit_original_response(content="Infos Valorant manquantes pour le leader.")
            return

        code: str = generate_team_code()
        created_at: datetime.datetime = datetime.datetime.utcnow()

        forum_channel: Optional[discord.ForumChannel] = await get_forum_channel(self.bot)
        if not forum_channel:
            await interaction.edit_original_response(content="Forum channel invalide.")
            return

        if visibility.value == "public":
            content: str = (
                f"Équipe créée par {leader.mention}\n"
                f"Code secret : ||{code}||\n"
                f"Région Leader : {leader_info['region']}\n"
                f"Visibilité : {visibility.name.capitalize()}"
            )
        else:
            content = (
                f"Équipe créée par {leader.mention}\n"
                f"Région Leader : {leader_info['region']}\n"
                f"Visibilité : {visibility.name.capitalize()}"
            )

        from .team_views import TeamForumJoinButtonView, TeamForumPrivateView
        view = TeamForumJoinButtonView(self, code) if visibility.value == "public" else TeamForumPrivateView(self, code)

        try:
            post = await forum_channel.create_thread(
                name=f"Équipe de {leader.display_name}",
                content=content,
                view=view
            )
        except Exception as e:
            await interaction.edit_original_response(content=f"Erreur création thread : {e}")
            return

        real_thread: discord.Thread = post.thread
        thread_id: int = real_thread.id

        success: bool = await MatchmakingService.create_team(
            code, leader.id, forum_channel.id, thread_id, visibility.value, created_at
        )
        if not success:
            await interaction.edit_original_response(content="Erreur lors de la création de l'équipe en base.")
            return

        ok: bool = await MatchmakingService.add_member_to_team(code, leader.id)
        if not ok:
            await interaction.edit_original_response(content="Erreur lors de l'ajout du leader à l'équipe.")
            return

        if visibility.value == "public":
            await real_thread.send(f"Code secret : **{code}**\nRejoignez l'équipe avec `/join_team {code}`.")

        await interaction.edit_original_response(
            content=(f"Équipe créée !\nPost : {real_thread.jump_url}\nCode : {code}\n"
                     f"Visibilité : {visibility.name.capitalize()}")
        )

    @app_commands.command(name="join_team", description="Rejoindre une équipe via son code.")
    async def join_team(self, interaction: discord.Interaction, code: str) -> None:
        """
        Permet à un utilisateur de rejoindre une équipe existante si celle-ci n'est pas complète.
        """
        await interaction.response.defer(ephemeral=True)
        code = code.strip().upper()

        team: Optional[Dict[str, Any]] = await MatchmakingService.get_team(code)
        if not team:
            await interaction.edit_original_response(content="Équipe introuvable ou expirée.")
            return

        if await MatchmakingService.is_user_in_any_team(interaction.user.id):
            await interaction.edit_original_response(content="Vous êtes déjà membre d'une équipe. Impossible d'en rejoindre une autre.")
            return

        lock = self.get_team_lock(code)
        async with lock:
            members: List[int] = await MatchmakingService.get_team_members(code)
            if len(members) >= 5:
                await interaction.edit_original_response(content="Cette équipe est déjà complète (5).")
                return

            leader_info = await MatchmakingService.get_user_info(team["leader_id"])
            user_info = await MatchmakingService.get_user_info(interaction.user.id)
            if not leader_info or not user_info:
                await interaction.edit_original_response(content="Infos Valorant manquantes.")
                return
            if user_info["region"] != leader_info["region"]:
                await interaction.edit_original_response(content="Région différente du leader.")
                return

            if not await MatchmakingService.add_member_to_team(code, interaction.user.id):
                await interaction.edit_original_response(content="Erreur lors de l'ajout à l'équipe.")
                return

            await self.update_team_thread(code)
            await interaction.edit_original_response(content="Vous avez rejoint l'équipe !")

            members = await MatchmakingService.get_team_members(code)
            if len(members) == 5:
                await self.create_voice_channel_and_invite(team)

    @app_commands.command(name="kick_member", description="Expulser un membre (leader seulement).")
    async def kick_member(self, interaction: discord.Interaction, code: str, member: discord.Member) -> None:
        """
        Permet au leader d'expulser un membre de l'équipe.
        """
        await interaction.response.defer(ephemeral=True)
        code = code.strip().upper()

        team = await MatchmakingService.get_team(code)
        if not team:
            await interaction.edit_original_response(content="Équipe introuvable.")
            return

        if interaction.user.id != team["leader_id"]:
            await interaction.edit_original_response(content="Vous n'êtes pas le leader.")
            return

        lock = self.get_team_lock(code)
        async with lock:
            members = await MatchmakingService.get_team_members(code)
            if member.id not in members:
                await interaction.edit_original_response(content="Ce membre n'est pas dans l'équipe.")
                return

            if not await MatchmakingService.remove_member_from_team(code, member.id):
                await interaction.edit_original_response(content="Erreur lors du retrait du membre.")
                return

            await self.update_team_thread(code)
            await interaction.edit_original_response(content=f"{member.display_name} expulsé.")

            members = await MatchmakingService.get_team_members(code)
            if len(members) == 0:
                await self.delete_team_resources(team)
                self.remove_team_lock(code)

    @app_commands.command(name="delete_team", description="Supprimer une équipe (admin ou leader).")
    @app_commands.describe(code="Le code de l'équipe à supprimer.")
    async def delete_team(self, interaction: discord.Interaction, code: str) -> None:
        """
        Supprime une équipe ainsi que ses ressources (thread et salon vocal). Seul le leader ou un admin peut le faire.
        """
        await interaction.response.defer(ephemeral=True)
        code = code.strip().upper()

        team = await MatchmakingService.get_team(code)
        if not team:
            await interaction.edit_original_response(content="Équipe introuvable ou déjà supprimée.")
            return

        user: discord.Member = interaction.user
        is_admin = any(r.permissions.administrator for r in user.roles)
        if not is_admin and user.id != team["leader_id"]:
            await interaction.edit_original_response(content="Vous n'avez pas la permission de supprimer cette équipe.")
            return

        lock = self.get_team_lock(code)
        async with lock:
            await self.delete_team_resources(team)
            if await MatchmakingService.delete_team(code):
                await interaction.edit_original_response(content=f"L'équipe {code} a été supprimée.")
                logger.info(f"Équipe {code} supprimée par {user.id}.")
            else:
                await interaction.edit_original_response(content="Erreur lors de la suppression de l'équipe.")
            self.remove_team_lock(code)

    @app_commands.command(name="list_teams", description="Liste toutes les équipes publiques.")
    async def list_teams(self, interaction: discord.Interaction) -> None:
        """
        Affiche la liste des équipes publiques disponibles.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            teams = await MatchmakingService.get_public_teams()
            if not teams:
                await interaction.edit_original_response(content="Aucune équipe publique disponible.")
                return

            msg: str = "### Équipes Publiques Disponibles:\n"
            for t in teams:
                leader = interaction.guild.get_member(t["leader_id"])
                leader_mention = leader.mention if leader else f"<@{t['leader_id']}>"
                msg += f"- **Code**: {t['code']} | **Leader**: {leader_mention} | **Visibilité**: {t['visibility']}\n"
            await interaction.edit_original_response(content=msg)
        except Exception as e:
            logger.error(f"Erreur list_teams: {e}")
            await interaction.edit_original_response(content="Erreur lors de la récupération des équipes publiques.")

    # ------------------------------------------------
    # Tâche de cleanup (équipes >24h)
    # ------------------------------------------------

    @tasks.loop(hours=1)
    async def cleanup_teams_task(self) -> None:
        """
        Supprime les équipes créées il y a plus de 24h.
        """
        logger.info("Nettoyage des équipes obsolètes...")
        try:
            old_teams = await MatchmakingService.get_teams_older_than(hours=24)
            for t in old_teams:
                code = t["code"]
                logger.info(f"Suppression de l'équipe obsolète: {code}")
                lock = self.get_team_lock(code)
                async with lock:
                    await self.delete_team_resources(t)
                    if await MatchmakingService.delete_team(code):
                        logger.info(f"Équipe obsolète {code} supprimée en BD.")
                    else:
                        logger.error(f"Échec de la suppression de l'équipe {code} en BD.")
                self.remove_team_lock(code)
        except Exception as e:
            logger.error(f"Erreur dans la tâche de nettoyage des équipes : {e}")

    @cleanup_teams_task.before_loop
    async def before_cleanup_teams_task(self) -> None:
        await self.bot.wait_until_ready()
        logger.info("Tâche de nettoyage des équipes (obsolètes) prête à démarrer.")

    # ------------------------------------------------
    # Gestion des ressources (threads et salons vocaux)
    # ------------------------------------------------

    async def update_team_thread(self, code: str) -> None:
        """
        Met à jour l'embed du thread dans le ForumChannel pour une équipe donnée.
        """
        team = await MatchmakingService.get_team(code)
        if not team:
            logger.warning(f"update_team_thread: Équipe {code} introuvable.")
            return

        members: List[int] = await MatchmakingService.get_team_members(code)
        forum_channel = self.bot.get_channel(team["forum_channel_id"])
        if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
            logger.error(f"forum_channel invalide pour {code}.")
            return

        guild: discord.Guild = forum_channel.guild
        thread = forum_channel.get_thread(team["thread_id"])
        if not thread:
            logger.error(f"Thread introuvable pour {code}.")
            return

        desc: str = f"Code secret : ||{team['code']}||" if team["visibility"] == "public" else "Équipe Privée"
        leader = guild.get_member(team["leader_id"])
        leader_mention = leader.mention if leader else f"<@{team['leader_id']}>"

        embed = discord.Embed(
            title="Équipe",
            description=f"**Leader :** {leader_mention}\n{desc}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Visibilité", value=team["visibility"].capitalize(), inline=False)

        for mid in members:
            member = guild.get_member(mid)
            if not member:
                continue
            info = await MatchmakingService.get_user_info(mid)
            elo = info["elo"] if info else "??"
            region = info["region"] if info else "??"
            line = f"{member.mention} (MMR={elo}, Région={region})"
            if mid == team["leader_id"]:
                line += " **(Leader)**"
            embed.add_field(name=member.display_name, value=line, inline=False)

        try:
            msgs = [m async for m in thread.history(limit=1)]
            if msgs:
                await msgs[0].edit(embed=embed)
            else:
                await thread.send(embed=embed)
        except Exception as e:
            logger.error(f"Erreur update_team_thread {code}: {e}")

    async def create_voice_channel_and_invite(self, team: Dict[str, Any]) -> None:
        """
        Crée un salon vocal pour l'équipe lorsque celle-ci atteint 5 membres, puis envoie l'invitation dans le thread.
        """
        forum_channel = self.bot.get_channel(team["forum_channel_id"])
        if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
            logger.error(f"Forum channel invalide pour l'équipe '{team['code']}'.")
            return

        guild = forum_channel.guild
        thread = forum_channel.get_thread(team["thread_id"])
        if not thread:
            logger.error(f"Thread introuvable pour l'équipe '{team['code']}'.")
            return

        category = await get_voice_category(guild)
        if not category:
            return

        overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
        mem_ids = await MatchmakingService.get_team_members(team["code"])
        for mid in mem_ids:
            member = guild.get_member(mid)
            if member:
                overwrites[member] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)

        try:
            vc = await guild.create_voice_channel(
                name=f"Team-{team['code']}",
                category=category,
                overwrites=overwrites
            )
            await MatchmakingService.update_voice_channel_id(team["code"], vc.id)
            logger.info(f"Salon vocal '{vc.name}' créé pour l'équipe {team['code']}.")

            invite = await vc.create_invite(max_uses=1, unique=True, reason="Équipe 5 stack formée.")
            await thread.send(f"Salon vocal créé : {invite.url}")
            logger.info(f"Invitation envoyée (thread={thread.id}) pour l'équipe {team['code']}.")
        except Exception as e:
            logger.error(f"Erreur création vocal pour l'équipe {team['code']}: {e}")

    async def delete_team_resources(self, team: Dict[str, Any]) -> None:
        """
        Supprime les ressources associées à une équipe (thread et salon vocal).
        """
        forum_channel = self.bot.get_channel(team["forum_channel_id"])
        if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
            logger.error(f"Forum channel invalide pour team '{team['code']}'.")
            return

        guild = forum_channel.guild
        thread = forum_channel.get_thread(team["thread_id"])
        if thread and not thread.archived:
            try:
                await thread.delete(reason="Équipe dissoute (thread).")
                logger.info(f"Thread équipe '{team['code']}' supprimé.")
            except Exception as e:
                logger.error(f"Erreur suppression thread team={team['code']}: {e}")

        vc_id = team.get("voice_channel_id")
        if vc_id:
            vc = guild.get_channel(vc_id)
            if vc and isinstance(vc, discord.VoiceChannel):
                try:
                    await vc.delete(reason="Équipe dissoute (vocal).")
                    logger.info(f"Salon vocal '{vc.name}' supprimé.")
                except Exception as e:
                    logger.error(f"Erreur suppression vocal team={team['code']}: {e}")

    # ------------------------------------------------
    # Gestion des verrous (locks) par équipe
    # ------------------------------------------------

    def get_team_lock(self, code: str) -> asyncio.Lock:
        """
        Retourne le lock dédié à l'équipe identifiée par le code.
        """
        if code not in self.team_locks:
            self.team_locks[code] = asyncio.Lock()
        return self.team_locks[code]

    def remove_team_lock(self, code: str) -> None:
        """
        Supprime le lock associé à l'équipe identifiée par le code, s'il existe.
        """
        if code in self.team_locks:
            del self.team_locks[code]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TeamManager(bot))
    logger.info("TeamManager chargé.")
