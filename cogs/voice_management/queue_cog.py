# cogs/voice_management/queue_cog.py

import asyncio
from datetime import datetime, timezone
import logging
import random
import string
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Tuple

import discord
from discord.ext import commands, tasks

from cogs.voice_management.services.five_stack_service import MatchmakingService

# Seuil pour la différence d'ELO autorisée entre les membres d'un groupe
ELO_DIFF_THRESHOLD = 300

logger = logging.getLogger(__name__)


class MatchmakingQueue(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Dictionnaire pour stocker les messages persistants de la queue par guild : {guild_id: (channel_id, message_id)}
        self.queue_status_embed_message: Dict[int, Tuple[int, int]] = {}
        self.lock = asyncio.Lock()
        self.process_queue_task_loop.start()   # démarrage unique de la boucle principale
        self.stale_task.start()               # démarrage de la tâche de stale

        # Compteurs pour suivre le nombre de joueurs par rôle
        self.role_counters = {
            "duelist": 0,
            "controller": 0,
            "sentinel": 0,
            "initiator": 0,
            "fill": 0
        }
        # self.total_teams_created = 0  # si besoin, sinon supprimer

    def cog_unload(self) -> None:
        self.process_queue_task_loop.cancel()
        self.stale_task.cancel()


    @tasks.loop(minutes=1)
    async def stale_task(self) -> None:
        """
        Gère automatiquement :
         - Conversion en 'any' après 5 minutes
         - Suppression après 10 minutes
        """
        mins_any = 5
        mins_remove = 10

        # Récupère toutes les entrées et filtre en Python
        entries = await MatchmakingService.get_queue_entries()
        if not entries:
            return

        now = datetime.now(timezone.utc)
        to_update = []

        for entry in entries:
            eid = entry["id"]
            user_id = entry["discord_member_id"]

            # Si timestamp est naïf (sans tz), on le marque en UTC
            ts = entry["timestamp"]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            age = (now - ts).total_seconds() / 60

            if age >= mins_remove:
                # Suppression définitive
                if await MatchmakingService.remove_entry(eid):
                    to_update.append(entry)
                    try:
                        user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                        await user.send(
                            "⏰ Votre inscription à la queue a été supprimée car vous étiez en attente depuis plus de 10 minutes."
                        )
                    except:
                        logger.warning(f"Impossible de DM pour suppression stale: {user_id}")

            elif age >= mins_any and entry["team_size"] != 0:
                # Passage en "any"
                if await MatchmakingService.update_entry_team_size_any(eid):
                    to_update.append(entry)
                    try:
                        user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                        await user.send(
                            "🔄 Votre préférence de taille a été passée à **N'importe** "
                            "car vous étiez en attente depuis plus de 5 minutes."
                        )
                    except:
                        logger.warning(f"Impossible de DM pour conversion any: {user_id}")

        # Rafraîchir l'embed uniquement si on a modifié au moins une entrée
        if to_update:
            for guild_id in self.queue_status_embed_message:
                await self.update_queue_status_embed(guild_id)

    @stale_task.before_loop
    async def before_stale(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------
    # Listeners
    # ------------------------------------------------

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        logger.info("MatchmakingQueue: on_ready déclenché.")
        for guild in self.bot.guilds:
            server_id = await MatchmakingService.get_server_id_by_guild_id(guild.id)
            if not server_id:
                logger.warning(f"Serveur introuvable pour la guilde={guild.id}.")
                continue

            # Initialisation du cache des rôles filtrés
            await MatchmakingService.initialize_filtered_roles_cache(guild.id)

            # Récupération du message persistant pour la queue
            data = await MatchmakingService.get_persistent_message(guild.id, "queue_status")
            if data:
                channel_id, message_id = data
                self.queue_status_embed_message[guild.id] = (channel_id, message_id)
                channel = guild.get_channel(channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(message_id)
                        from .queue_views import QueueView
                        view = QueueView(self, guild.id)
                        await message.edit(view=view)
                        logger.info(f"QueueView réassignée pour guild={guild.id}.")
                    except Exception as e:
                        logger.error(f"Erreur lors de la réassignation de QueueView pour guild={guild.id}: {e}")

        logger.info("MatchmakingQueue est prêt.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """
        Si le membre est leader d'une équipe, retire l'équipe entière.
        """
        await self.handle_team_member_leave(member)

    # ------------------------------------------------
    # Commandes
    # ------------------------------------------------

    @commands.command(name="start_queue")
    @commands.has_permissions(administrator=True)
    async def start_queue(self, ctx: commands.Context) -> None:
        """
        Commande pour poster l'embed principal de la queue et la QueueView.
        """
        from .queue_views import QueueView

        embed = await self.create_queue_embed(ctx.guild.id)
        view = QueueView(self, ctx.guild.id)
        msg = await ctx.send(embed=embed, view=view)

        self.queue_status_embed_message[ctx.guild.id] = (ctx.channel.id, msg.id)
        await MatchmakingService.save_persistent_message(ctx.guild.id, "queue_status", ctx.channel.id, msg.id)

        await ctx.send("Queue initialisée et persistée.")

    # ------------------------------------------------
    # Tâche de boucle pour le traitement de la queue
    # ------------------------------------------------

    @tasks.loop(seconds=15)
    async def process_queue_task_loop(self) -> None:
        """
        Boucle qui tente de former des groupes toutes les 15 secondes en utilisant une approche gloutonne.
        """
        async with self.queue_lock():
            entries = await MatchmakingService.get_queue_entries()
            if not entries:
                logger.debug("Queue vide.")
                return

            # Regroupement par (langue, region, platform, team_size)
            grouped = self.group_entries(entries)

            # Ordre de priorité : -1 (n'importe) puis 5, 3, 2
            team_size_priority = [5, 3, 2, -1]

            for desired_size in team_size_priority:
                for group_key, group_entries in list(grouped.items()):
                    lang, region, platf, tsize = group_key

                    if tsize == -1:
                        # Pour les entrées génériques, essayer différentes tailles
                        for size in [5, 3, 2]:
                            await self.form_groups_greedy(group_entries, size, group_key)
                    elif tsize == desired_size:
                        await self.form_groups_greedy(group_entries, desired_size, group_key)

                    # Mise à jour de la liste des entrées après modification
                    entries = await MatchmakingService.get_queue_entries()
                    grouped = self.group_entries(entries)

    @asynccontextmanager
    async def queue_lock(self):
        async with self.lock:
            yield

    # ------------------------------------------------
    # Regroupement des entrées
    # ------------------------------------------------

    def group_entries(self, entries: List[Dict]) -> Dict[Tuple[str, str, str, int], List[Dict]]:
        """
        Regroupe les entrées selon (langue, region, platform, team_size).
        """
        grouped: Dict[Tuple[str, str, str, int], List[Dict]] = {}
        for e in entries:
            key = (e["langue"], e["region"], e["platform"], e["team_size"])
            grouped.setdefault(key, []).append(e)
        return grouped

    # ------------------------------------------------
    # Formation gloutonne de groupes
    # ------------------------------------------------

    async def form_groups_greedy(
        self, blocks: List[Dict], desired_size: int, group_key: Tuple[str, str, str, int]
    ) -> None:
        """
        Tente de former un groupe en combinant les blocs pour atteindre une somme d'entry_type égale à desired_size.
        Vérifie ensuite l'écart ELO, la condition mmr_extended et la diversité des rôles.
        """
        if desired_size not in [2, 3, 5]:
            return

        if not blocks:
            return

        used_blocks = []
        sum_type = 0
        combined_elos = []
        combined_roles = []

        for b in blocks:
            if sum_type + b["entry_type"] <= desired_size:
                sum_type += b["entry_type"]
                used_blocks.append(b)
                if b["elo"] is not None:
                    combined_elos.append(b["elo"])
                combined_roles.extend(b["roles"])

                if sum_type == desired_size:
                    if combined_elos:
                        elo_high = max(combined_elos)
                        elo_low = min(combined_elos)
                        if (elo_high - elo_low) > ELO_DIFF_THRESHOLD:
                            if not all(x.get("mmr_extended", False) for x in used_blocks):
                                logger.debug("Écart ELO trop important sans mmr_extended pour certains blocs, abandon.")
                                return
                    else:
                        logger.debug("Aucun ELO disponible, impossible de former un groupe.")
                        return

                    unique_roles = set(combined_roles)
                    if len(unique_roles) < desired_size:
                        logger.debug("Rôles insuffisamment diversifiés, mais le groupe sera formé.")
                    await self.build_final_group(used_blocks, desired_size)
                    return

    async def build_final_group(self, blocks: List[Dict], desired_size: int) -> None:
        """
        Finalise la formation du groupe :
        - Récupère les membres
        - Crée un salon vocal
        - Décrémente les compteurs de rôles
        - Supprime les blocs de la queue
        - Met à jour l'embed de la queue
        """
        # 1. Récupération de tous les IDs
        all_ids = []
        for b in blocks:
            tmids = b.get("team_member_ids")
            if tmids:
                all_ids.extend(tmids)
            else:
                all_ids.append(b["discord_member_id"])
        all_ids = list(set(all_ids))

        # 2. Vérification cohérence et création du salon
        group_members = await MatchmakingService.get_members_from_ids(all_ids)
        if len(group_members) != sum(b["entry_type"] for b in blocks):
            logger.warning("Incohérence dans le nombre de membres récupérés.")
            return

        await self.create_voice_channel(group_members)

        # 3. Pour chaque bloc : décrémenter les compteurs de rôles puis retirer du queue
        for b in blocks:
            # a) Décrémentation des compteurs pour les rôles de ce bloc
            for r in b.get("roles", []):
                if r in self.role_counters:
                    self.role_counters[r] = max(0, self.role_counters[r] - 1)

            # b) Suppression du bloc dans la DB
            tmids = b.get("team_member_ids")
            if tmids:
                await MatchmakingService.remove_players_from_queue(tmids)
            else:
                await MatchmakingService.remove_players_from_queue([b["discord_member_id"]])

        # 4. Mise à jour de l'embed de statut
        guild_id = group_members[0].guild.id
        await self.update_queue_status_embed(guild_id)

        logger.info(f"[MATCH] Groupe de {desired_size} formé avec les IDs : {all_ids}")

    @commands.command(name="role_counters", help="Affiche les compteurs de rôles actuels dans la queue.")
    @commands.has_permissions(administrator=True)
    async def role_counters(self, ctx: commands.Context) -> None:
        """
        Affiche le nombre actuel de joueurs en attente par rôle.
        Réservé aux administrateurs.
        """
        if not self.role_counters:
            await ctx.send("Aucun compteur de rôles n'est configuré.")
            return

        # Prépare un embed pour un affichage plus lisible
        embed = discord.Embed(
            title="🔢 Compteurs de Rôles Actuels",
            color=discord.Color.blue()
        )
        for role, count in self.role_counters.items():
            embed.add_field(name=role.capitalize(), value=str(count), inline=True)

        await ctx.send(embed=embed)


    # ------------------------------------------------
    # Création du salon vocal
    # ------------------------------------------------

    async def create_voice_channel(self, group: List[discord.Member]) -> Optional[discord.VoiceChannel]:
        """
        Crée un salon vocal pour le groupe et envoie à chaque membre un embed
        avec un gros bouton vert “Rejoindre le canal vocal” et un listing clair des rôles.
        """
        if not group:
            return None

        guild = group[0].guild
        # --- Création / récupération de la catégorie ---
        category = discord.utils.get(guild.categories, name="Matchmaking")
        if not category:
            category = await guild.create_category("Matchmaking")

        # --- Permissions du canal ---
        overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
        for m in group:
            overwrites[m] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)

        try:
            # 1) Création du salon vocal et de l'invitation
            vc_name = "Team-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
            vc = await guild.create_voice_channel(vc_name, category=category, overwrites=overwrites)
            invite = await vc.create_invite(max_uses=len(group), unique=True, reason="Matchmaking formed")

            # 2) Construction de l'embed
            embed = discord.Embed(
                title="🚀 Votre Équipe Valorant est Prête !",
                description="Cliquez sur le bouton ci-dessous pour rejoindre directement le canal vocal.",
                color=discord.Color.green()
            )

            # Pour plus d'aération, on aligne deux champs côte à côte si on veut,
            # mais ici on utilise un champ unique listant tous les membres.
            # 3) Récupération des rôles et construction de la valeur du champ
            lines = []
            for m in group:
                roles_list = await MatchmakingService.get_roles_for_discord_member(m.id) or []
                # Capitalize chaque rôle et joindre, ou indiquer "Aucun rôle"
                roles_display = ", ".join(r.capitalize() for r in roles_list) or "Aucun rôle"
                lines.append(f"**{m.display_name}** — {roles_display}")

            embed.add_field(name="🎭 Membres & Rôles", value="\n".join(lines), inline=False)
            embed.set_footer(text="Bon match à tous !")
            embed.timestamp = discord.utils.utcnow()

            # 4) Création d’une View avec un bouton vert (success)
            class JoinVCView(discord.ui.View):
                def __init__(self, invite_url: str, vc_name: str):
                    super().__init__(timeout=None)
                    self.invite_url = invite_url
                    self.vc_name = vc_name

                @discord.ui.button(
                    label="Rejoindre le canal vocal",
                    style=discord.ButtonStyle.success,
                    custom_id=f"join_vc_{vc.id}"
                )
                async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
                    await interaction.response.send_message(
                        f"📣 Vous pouvez rejoindre **{self.vc_name}** ici : {self.invite_url}",
                        ephemeral=True
                    )

            view = JoinVCView(invite.url, vc.name)

            # 5) Envoi du même embed + bouton à chaque membre
            for m in group:
                try:
                    await m.send(embed=embed, view=view)
                except Exception as e:
                    logger.error(f"Impossible d'envoyer le DM embed à {m.display_name} : {e}")

            return vc

        except Exception as e:
            logger.error(f"Erreur création salon + embed corrigé : {e}")
            return None
   
    # ------------------------------------------------
    # Création et mise à jour de l'embed de la queue
    # ------------------------------------------------

    async def create_queue_embed(self, guild_id: int) -> discord.Embed:
        """
        Construit l'embed principal affichant :
        - Solos en attente
        - Équipes en attente
        - Total d'entrées dans la queue
        - Rôle prioritaire (celui avec le plus faible compteur)
        """
        total_solo = await MatchmakingService.count_solos_in_queue()
        total_team = await MatchmakingService.count_teams_in_queue()
        total_entries = await MatchmakingService.count_total_players_in_queue()

        embed = discord.Embed(
            title="Rejoignez la Queue Valorant",
            description="Choisissez la taille de votre équipe pour rejoindre.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Solos en attente", value=str(total_solo), inline=True)
        embed.add_field(name="Équipes en attente", value=str(total_team), inline=True)
        embed.add_field(name="Joueurs totaux", value=str(total_entries), inline=True)

        if self.role_counters:
            priority_role = min(self.role_counters, key=self.role_counters.get)
            embed.add_field(name="Rôle Prioritaire", value=priority_role.capitalize(), inline=False)
        else:
            embed.add_field(name="Rôle Prioritaire", value="N/A", inline=False)

        embed.set_footer(text="Mise à jour automatique toutes les 15 secondes.")
        return embed

    async def update_queue_status_embed(self, guild_id: int) -> None:
        data = self.queue_status_embed_message.get(guild_id)
        if not data:
            return
        channel_id, message_id = data
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
            embed = await self.create_queue_embed(guild_id)
            from .queue_views import QueueView
            view = QueueView(self, guild_id)
            await message.edit(embed=embed, view=view)
            logger.info(f"Embed de la queue mis à jour pour guild={guild_id}.")
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de l'embed pour guild={guild_id} : {e}")

    # ------------------------------------------------
    # Gestion des membres et des équipes dans la queue
    # ------------------------------------------------

    async def remove_from_queue(self, user: discord.Member) -> None:
        async with self.queue_lock():
            # Récupérer les rôles avant suppression
            roles = await MatchmakingService.get_roles_for_discord_member(user.id) or []

            removed = await MatchmakingService.remove_player_from_queue(user.id)
            if not removed:
                raise ValueError("Vous n'êtes pas dans la queue.")

            # Décrémentation des compteurs de rôles
            for r in roles:
                if r in self.role_counters:
                    self.role_counters[r] = max(0, self.role_counters[r] - 1)

            await self.update_queue_status_embed(user.guild.id)
            logger.info(f"{user.display_name} a été retiré de la queue.")

    async def handle_team_member_leave(self, member: discord.Member) -> None:
        """
        Si le membre est leader d'une équipe, retire l'équipe entière.
        """
        async with self.queue_lock():
            team_code = await MatchmakingService.is_user_leader_of_team(member.id)
            if team_code:
                team_members = await MatchmakingService.get_team_members(team_code)
                await MatchmakingService.remove_players_from_queue(team_members)
                await self.update_queue_status_embed(member.guild.id)
                logger.info(f"Équipe {team_code} retirée suite au départ de {member.display_name}.")

    # ------------------------------------------------
    # Ajout d'entrées dans la queue
    # ------------------------------------------------

    async def add_solo_to_queue(
        self,
        user: discord.Member,
        langue: str,
        region: str,
        platform: str,
        team_size: int,
        mmr_extended: bool,
        elo: int,
        roles: List[str]
    ) -> None:
        async with self.queue_lock():
            if await MatchmakingService.is_user_leader_of_team(user.id):
                raise ValueError("Déjà leader d'une équipe, impossible de rejoindre en solo.")

            await MatchmakingService.add_entry_to_queue(
                entry_type=1,
                discord_member_id=user.id,
                team_member_ids=None,
                langue=langue,
                region=region,
                platform=platform,
                team_size=team_size,
                mmr_extended=mmr_extended,
                elo=elo,
                elo_high=elo,
                elo_low=elo,
                roles=roles
            )

            for r in roles:
                if r in self.role_counters:
                    self.role_counters[r] += 1

            await self.update_queue_status_embed(user.guild.id)
            logger.info(f"[Queue] Solo ajouté : {user.display_name} avec rôles {roles}")

    async def add_group_to_queue(
        self,
        leader: discord.Member,
        members: List[discord.Member],
        langue: str,
        region: str,
        platform: str,
        team_size: int,
        mmr_extended: bool,
        elo_moy: int,
        elo_high: int,
        elo_low: int,
        roles: List[str]
    ) -> None:
        """
        Ajoute une équipe partielle (duo, trio ou quatuor) dans la queue.
        """
        async with self.queue_lock():
            for m in members:
                if await MatchmakingService.is_user_leader_of_team(m.id):
                    raise ValueError(f"{m.display_name} est déjà leader d'une autre équipe.")

            entry_type = len(members)
            if entry_type not in [2, 3, 4]:
                raise ValueError("Le groupe doit être un duo, trio ou quatuor.")

            all_ids = [m.id for m in members]

            await MatchmakingService.add_entry_to_queue(
                entry_type=entry_type,
                discord_member_id=leader.id,
                team_member_ids=all_ids,
                langue=langue,
                region=region,
                platform=platform,
                team_size=team_size,
                mmr_extended=mmr_extended,
                elo=elo_moy,
                elo_high=elo_high,
                elo_low=elo_low,
                roles=roles
            )

            await self.update_queue_status_embed(leader.guild.id)
            logger.info(f"[Queue] Groupe partiel ajouté (taille={entry_type}) par {leader.display_name}")

    async def add_preformed_team_to_queue(
        self,
        leader: discord.Member,
        desired_size: int,  # 2, 3, 5 ou 0 ("n'importe")
        mmr_extended: bool,
        langue: str,
        region: str,
        platform: str,
        roles: List[str]
    ) -> None:
        """
        Ajoute une équipe préformée dans la queue après vérification du leadership.
        """
        code = await MatchmakingService.is_user_leader_of_team(leader.id)
        if not code:
            raise ValueError("Vous n'êtes pas le leader d'une équipe.")

        member_ids = await MatchmakingService.get_team_members(code)
        if not member_ids:
            raise ValueError("Votre équipe est vide. Impossible de rejoindre la queue.")

        total_elo = 0
        elo_high = -999999
        elo_low = 999999
        valid_members = []
        for mid in member_ids:
            user_info = await MatchmakingService.get_user_info(mid)
            if not user_info:
                raise ValueError(f"Le membre {mid} n'a pas d'information Valorant.")
            e = user_info["elo"]
            total_elo += e
            if e > elo_high:
                elo_high = e
            if e < elo_low:
                elo_low = e
            valid_members.append(mid)

        if not valid_members:
            raise ValueError("Aucun membre valide dans l'équipe.")

        elo_moy = total_elo // len(valid_members)

        entry_type = len(valid_members)
        await MatchmakingService.add_entry_to_queue(
            entry_type=entry_type,
            discord_member_id=leader.id,
            team_member_ids=valid_members,
            langue=langue,
            region=region,
            platform=platform,
            team_size=desired_size,
            mmr_extended=mmr_extended,
            elo=elo_moy,
            elo_high=elo_high,
            elo_low=elo_low,
            roles=roles
        )

        for r in roles:
            if r in self.role_counters:
                self.role_counters[r] += 1

        await self.update_queue_status_embed(leader.guild.id)
        self.bot.logger.info(f"[Queue] Equipe ajoutée par {leader.display_name} avec rôles {roles}")
        logger.info(
            f"[Queue] Equipe '{code}' ajoutée en queue : entry_type={entry_type}, desired_size={desired_size}, "
            f"mmr_extended={mmr_extended}, elo_moy={elo_moy}, elo_high={elo_high}, elo_low={elo_low}, roles={roles}."
        )


# ------------------------------------------------
# Setup du cog
# ------------------------------------------------

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MatchmakingQueue(bot))
    logger.info("MatchmakingQueue chargé.")
