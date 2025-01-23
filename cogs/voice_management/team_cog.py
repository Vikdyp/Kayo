#cogs\voice_management\team_cog.py
import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
import random
import string
from typing import Optional, Dict, List
import datetime
import asyncio

# Import du service
from .services.five_stack_service import MatchmakingService

logger = logging.getLogger(__name__)

# Constantes
FORUM_CHANNEL_ID = 1325629700248178778  # ID réel de votre forum
VOICE_CATEGORY_NAME = "Matchmaking"     # Nom de la catégorie vocale


class TeamManager(commands.Cog):
    """
    Gère la création d'équipe via /create_team, /join_team,
    l'expulsion via /kick_member, et la suppression avec /delete_team.

    - Chaque équipe a un "code" unique.
    - On stocke l'équipe dans la table 'teams'.
    - Les membres dans 'team_members'.
    - Si l'équipe atteint 5 membres => create_voice_channel_and_invite(team).
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Verrous par code d'équipe => éviter les accès concurrents (join, kick, etc.)
        self.team_locks: Dict[str, asyncio.Lock] = {}

        # Au démarrage, on charge toutes les équipes existantes, puis on les supprime
        # (cela supprime aussi leurs threads + vocaux, selon ta logique).
        self.bot.loop.create_task(self.initialize())

        # Tâche de nettoyage des équipes obsolètes (toutes les heures)
        self.cleanup_teams_task.start()

    def cog_unload(self):
        self.cleanup_teams_task.cancel()

    # ------------------------------------------------
    # Initialisation du Cog
    # ------------------------------------------------

    async def initialize(self):
        """
        Au démarrage, on charge toutes les équipes existantes
        et on supprime TOUTES les entrées (threads/forums + vocal + BD).
        """
        await self.load_existing_teams()
        await self.delete_all_teams()
        logger.info("Initialisation du TeamManager terminée.")

    async def load_existing_teams(self):
        """
        Charge toutes les équipes pour log/debug.
        """
        try:
            teams = await MatchmakingService.get_all_teams()
            for t in teams:
                logger.info(f"Équipe existante chargée (BD): code={t['code']}")
            logger.info("Toutes les équipes existantes ont été chargées (log uniquement).")
        except Exception as e:
            logger.error(f"Erreur lors du chargement des équipes existantes : {e}")

    async def delete_all_teams(self):
        """
        Supprime TOUTES les équipes existantes (threads/forums + vocal + BD).
        """
        logger.info("Début de la suppression de toutes les équipes existantes (init).")
        try:
            teams = await MatchmakingService.get_all_teams()
            for t in teams:
                code = t["code"]
                logger.info(f"Suppression de l'équipe : {code}")
                # 1) Supprimer les ressources Discord (thread+vocal)
                await self.delete_team_resources(t)
                # 2) Supprimer en base de données
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
    async def create_team(self, interaction: discord.Interaction, visibility: app_commands.Choice[str]):
        """
        Crée un post dans le forum FORUM_CHANNEL_ID avec un code secret (si public).
        Y place une vue de type TeamForumJoinButtonView si c'est public, ou TeamForumPrivateView si privé.
        """
        await interaction.response.defer(ephemeral=True)
        leader = interaction.user

        # Vérifier si le leader est déjà dans une équipe
        existing = await MatchmakingService.is_user_in_any_team(leader.id)
        if existing:
            await interaction.edit_original_response(
                content="Vous êtes déjà membre d'une équipe."
            )
            return

        # Récup infos Valorant du leader
        leader_info = await MatchmakingService.get_user_info(leader.id)
        if not leader_info:
            await interaction.edit_original_response(
                content="Infos Valorant manquantes pour le leader."
            )
            return

        # Générer un code unique pour l'équipe
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        created_at = datetime.datetime.utcnow()

        forum_channel = self.bot.get_channel(FORUM_CHANNEL_ID)
        if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
            await interaction.edit_original_response(content="Forum channel invalide.")
            return

        # Construire le contenu du thread
        if visibility.value == "public":
            content = (
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
        if visibility.value == "public":
            view = TeamForumJoinButtonView(self, code)
        else:
            view = TeamForumPrivateView(self, code)

        try:
            post = await forum_channel.create_thread(
                name=f"Équipe de {leader.display_name}",
                content=content,
                view=view
            )
        except Exception as e:
            await interaction.edit_original_response(content=f"Erreur création thread : {e}")
            return

        real_thread = post.thread
        thread_id = real_thread.id

        # Créer l'équipe en base
        success = await MatchmakingService.create_team(
            code, leader.id, forum_channel.id, thread_id, visibility.value, created_at
        )
        if not success:
            await interaction.edit_original_response(
                content="Erreur lors de la création de l'équipe en base."
            )
            return

        # Ajouter le leader comme membre
        ok = await MatchmakingService.add_member_to_team(code, leader.id)
        if not ok:
            await interaction.edit_original_response(
                content="Erreur lors de l'ajout du leader à l'équipe."
            )
            return

        if visibility.value == "public":
            await real_thread.send(
                f"Code secret : **{code}**\n"
                f"Rejoignez l'équipe avec `/join_team {code}`."
            )

        await interaction.edit_original_response(
            content=(
                f"Équipe créée !\n"
                f"Post : {real_thread.jump_url}\n"
                f"Code : {code}\n"
                f"Visibilité : {visibility.name.capitalize()}"
            )
        )

    @app_commands.command(name="join_team", description="Rejoindre une équipe via son code.")
    async def join_team(self, interaction: discord.Interaction, code: str):
        """
        Permet de rejoindre une équipe existante si elle n'a pas déjà 5 membres.
        """
        await interaction.response.defer(ephemeral=True)
        code = code.strip().upper()

        team = await MatchmakingService.get_team(code)
        if not team:
            await interaction.edit_original_response(content="Équipe introuvable ou expirée.")
            return

        # Vérifier si l'utilisateur est déjà membre d'une équipe
        existing = await MatchmakingService.is_user_in_any_team(interaction.user.id)
        if existing:
            await interaction.edit_original_response(
                content="Vous êtes déjà membre d'une équipe. Impossible d'en rejoindre une autre."
            )
            return

        lock = self.get_team_lock(code)
        async with lock:
            members = await MatchmakingService.get_team_members(code)
            if len(members) >= 5:
                await interaction.edit_original_response(content="Cette équipe est déjà complète (5).")
                return

            # Vérif region
            leader_info = await MatchmakingService.get_user_info(team["leader_id"])
            user_info = await MatchmakingService.get_user_info(interaction.user.id)
            if not leader_info or not user_info:
                await interaction.edit_original_response(content="Infos Valorant manquantes.")
                return
            if user_info["region"] != leader_info["region"]:
                await interaction.edit_original_response(content="Région différente du leader.")
                return

            # Ajouter
            ok = await MatchmakingService.add_member_to_team(code, interaction.user.id)
            if not ok:
                await interaction.edit_original_response(content="Erreur lors de l'ajout à l'équipe.")
                return

            # Mettre à jour le thread
            await self.update_team_thread(code)

            await interaction.edit_original_response(content="Vous avez rejoint l'équipe !")

            # Vérifier si c'est 5 => create vocal
            members = await MatchmakingService.get_team_members(code)
            if len(members) == 5:
                await self.create_voice_channel_and_invite(team)

    @app_commands.command(name="kick_member", description="Expulser un membre (leader seulement).")
    async def kick_member(self, interaction: discord.Interaction, code: str, member: discord.Member):
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

            ok = await MatchmakingService.remove_member_from_team(code, member.id)
            if not ok:
                await interaction.edit_original_response(content="Erreur lors du retrait du membre.")
                return

            await self.update_team_thread(code)

            await interaction.edit_original_response(content=f"{member.display_name} expulsé.")

            # Vérifier si l'équipe est vide
            members = await MatchmakingService.get_team_members(code)
            if len(members) == 0:
                # Supprimer le salon vocal et le thread
                await self.delete_team_resources(team)
                # Supprimer le lock
                self.remove_team_lock(code)

    @app_commands.command(name="delete_team", description="Supprimer une équipe (admin ou leader).")
    @app_commands.describe(code="Le code de l'équipe à supprimer.")
    async def delete_team(self, interaction: discord.Interaction, code: str):
        """
        Supprime l'équipe, le thread, le salon vocal. 
        Leader ou admin.
        """
        await interaction.response.defer(ephemeral=True)
        code = code.strip().upper()

        team = await MatchmakingService.get_team(code)
        if not team:
            await interaction.edit_original_response(content="Équipe introuvable ou déjà supprimée.")
            return

        user = interaction.user
        # Vérifie si l'utilisateur est admin
        is_admin = any(r.permissions.administrator for r in user.roles)

        if not is_admin and user.id != team["leader_id"]:
            await interaction.edit_original_response(
                content="Vous n'avez pas la permission de supprimer cette équipe."
            )
            return

        lock = self.get_team_lock(code)
        async with lock:
            await self.delete_team_resources(team)
            success = await MatchmakingService.delete_team(code)
            if success:
                await interaction.edit_original_response(
                    content=f"L'équipe {code} a été supprimée."
                )
                logger.info(f"Équipe {code} supprimée par {user.id}.")
            else:
                await interaction.edit_original_response(
                    content="Erreur lors de la suppression de l'équipe."
                )
            self.remove_team_lock(code)

    @app_commands.command(name="list_teams", description="Liste toutes les équipes publiques.")
    async def list_teams(self, interaction: discord.Interaction):
        """
        Liste les équipes visibility='public'.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            teams = await MatchmakingService.get_public_teams()
            if not teams:
                await interaction.edit_original_response(content="Aucune équipe publique disponible.")
                return

            msg = "### Équipes Publiques Disponibles:\n"
            for t in teams:
                leader = interaction.guild.get_member(t["leader_id"])
                leader_mention = leader.mention if leader else f"<@{t['leader_id']}>"
                msg += (
                    f"- **Code**: {t['code']} | **Leader**: {leader_mention} | "
                    f"**Visibilité**: {t['visibility']}\n"
                )

            await interaction.edit_original_response(content=msg)
        except Exception as e:
            logger.error(f"Erreur list_teams: {e}")
            await interaction.edit_original_response(
                content="Erreur lors de la récupération des équipes publiques."
            )

    # ------------------------------------------------
    # Tâche de cleanup (équipes >24h)
    # ------------------------------------------------

    @tasks.loop(hours=1)
    async def cleanup_teams_task(self):
        """
        Supprime les équipes créées il y a plus de 24h (logique existante).
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
                    ok = await MatchmakingService.delete_team(code)
                    if ok:
                        logger.info(f"Équipe obsolète {code} supprimée en BD.")
                    else:
                        logger.error(f"Échec de la suppression de l'équipe {code} en BD.")
                self.remove_team_lock(code)
        except Exception as e:
            logger.error(f"Erreur dans la tâche de nettoyage des équipes : {e}")

    @cleanup_teams_task.before_loop
    async def before_cleanup_teams_task(self):
        await self.bot.wait_until_ready()
        logger.info("Tâche de nettoyage des équipes (obsolètes) prête à démarrer.")

    # ------------------------------------------------
    # Gestion des Ressources (threads+vocaux)
    # ------------------------------------------------

    async def update_team_thread(self, code: str):
        """
        Met à jour l'embed du thread ForumChannel pour l'équipe.
        """
        team = await MatchmakingService.get_team(code)
        if not team:
            logger.warning(f"update_team_thread: Équipe {code} introuvable.")
            return

        members = await MatchmakingService.get_team_members(code)

        forum_channel = self.bot.get_channel(team["forum_channel_id"])
        if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
            logger.error(f"forum_channel invalide pour {code}.")
            return

        guild = forum_channel.guild
        thread = forum_channel.get_thread(team["thread_id"])
        if not thread:
            logger.error(f"Thread introuvable pour {code}.")
            return

        desc = "Équipe Privée"
        if team["visibility"] == "public":
            desc = f"Code secret : ||{team['code']}||"

        # Récupérer l'objet Member du leader
        leader = guild.get_member(team["leader_id"])
        if not leader:
            logger.error(f"Leader avec l'ID {team['leader_id']} introuvable dans la guilde {guild.id}.")
            leader_mention = f"<@{team['leader_id']}>"
        else:
            leader_mention = leader.mention

        embed = discord.Embed(
            title="Équipe",  # Titre général sans mention
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


    async def create_voice_channel_and_invite(self, team: Dict):
        """
        Si l'équipe atteint 5 membres, on crée un salon vocal et on envoie l'invitation dans le thread.
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

        category = discord.utils.get(guild.categories, name=VOICE_CATEGORY_NAME)
        if not category:
            try:
                category = await guild.create_category(VOICE_CATEGORY_NAME)
                logger.info(f"Catégorie '{VOICE_CATEGORY_NAME}' créée.")
            except Exception as e:
                logger.error(f"Erreur création catégorie '{VOICE_CATEGORY_NAME}': {e}")
                return

        # Permissions
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False)
        }
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
            # update en BD
            await MatchmakingService.update_voice_channel_id(team["code"], vc.id)
            logger.info(f"Salon vocal '{vc.name}' créé pour l'équipe {team['code']}.")

            invite = await vc.create_invite(max_uses=1, unique=True, reason="Équipe 5 stack formée.")
            await thread.send(f"Salon vocal créé : {invite.url}")
            logger.info(f"Invitation envoyée (thread={thread.id}) pour l'équipe {team['code']}.")
        except Exception as e:
            logger.error(f"Erreur création vocal pour l'équipe {team['code']}: {e}")

    async def delete_team_resources(self, team: Dict):
        """
        Supprime le thread + le salon vocal associés à l'équipe.
        (Ne supprime pas directement l'équipe en BD,
         c'est fait par delete_team(...) ci-dessus ou dans delete_all_teams().)
        """
        forum_channel = self.bot.get_channel(team["forum_channel_id"])
        if not forum_channel or not isinstance(forum_channel, discord.ForumChannel):
            logger.error(f"Forum channel invalide pour team '{team['code']}'.")
            return

        guild = forum_channel.guild

        # Thread
        thread = forum_channel.get_thread(team["thread_id"])
        if thread and not thread.archived:
            try:
                await thread.delete(reason="Équipe dissoute (thread).")
                logger.info(f"Thread équipe '{team['code']}' supprimé.")
            except Exception as e:
                logger.error(f"Erreur supp thread team={team['code']}: {e}")

        # Salon vocal
        vc_id = team.get("voice_channel_id")
        if vc_id:
            vc = guild.get_channel(vc_id)
            if vc and isinstance(vc, discord.VoiceChannel):
                try:
                    await vc.delete(reason="Équipe dissoute (vocal).")
                    logger.info(f"Salon vocal '{vc.name}' supprimé.")
                except Exception as e:
                    logger.error(f"Erreur supp vocal team={team['code']}: {e}")

    # ------------------------------------------------
    # Gestion des verrous (locks) par équipe
    # ------------------------------------------------

    def get_team_lock(self, code: str) -> asyncio.Lock:
        """
        Retourne le lock dédié à l'équipe <code>.
        """
        if code not in self.team_locks:
            self.team_locks[code] = asyncio.Lock()
        return self.team_locks[code]

    def remove_team_lock(self, code: str):
        """
        Supprime le lock de l'équipe <code> si existant.
        """
        if code in self.team_locks:
            del self.team_locks[code]


# ------------------------------------------------
# Setup du cog
# ------------------------------------------------

async def setup(bot: commands.Bot):
    await bot.add_cog(TeamManager(bot))
    logger.info("TeamManager chargé.")
