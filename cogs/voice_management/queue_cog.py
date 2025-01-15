#cogs\voice_management\queue_cog.py
import asyncio
import logging
import random
import logging
import string
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Tuple

import discord
from discord.ext import commands, tasks

from cogs.voice_management.services.five_stack_service import MatchmakingService

logger = logging.getLogger(__name__)


class MatchmakingQueue(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queue_status_embed_message: Dict[int, Tuple[int, int]] = {}
        self.lock = asyncio.Lock()
        self.process_queue_task_loop.start()

        # On ajoute les compteurs si tu veux suivre le nombre de joueurs par rôle :
        self.role_counters = {
            "duelist": 0,
            "controller": 0,
            "sentinel": 0,
            "initiator": 0,
            "fill": 0
        }

        self.total_teams_created = 0  # Si tu veux suivre combien d'équipes formées


    def cog_unload(self):
        self.process_queue_task_loop.cancel()

    # ------------------------------------------------
    # Listeners
    # ------------------------------------------------

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("MatchmakingQueue: on_ready déclenché.")
        for guild in self.bot.guilds:
            server_id = await MatchmakingService.get_server_id_by_guild_id(guild.id)
            if not server_id:
                logger.warning(f"Serveur introuvable pour la guilde={guild.id}.")
                continue

            # Init cache rôles
            await MatchmakingService.initialize_filtered_roles_cache(guild.id)

            # Récup le message persistant
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
                        logger.error(f"Erreur reassign QueueView guild={guild.id}: {e}")

        logger.info("MatchmakingQueue est prêt.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """
        Si le membre est leader d'une team, on retire la team entière.
        """
        await self.handle_team_member_leave(member)

    # ------------------------------------------------
    # Commandes
    # ------------------------------------------------

    @commands.command(name="start_queue")
    @commands.has_permissions(administrator=True)
    async def start_queue(self, ctx: commands.Context):
        """
        Commande pour poster l'embed principal de la file + la QueueView.
        """
        from .queue_views import QueueView

        embed = await self.create_queue_embed(ctx.guild.id)
        view = QueueView(self, ctx.guild.id)
        msg = await ctx.send(embed=embed, view=view)

        self.queue_status_embed_message[ctx.guild.id] = (ctx.channel.id, msg.id)
        await MatchmakingService.save_persistent_message(ctx.guild.id, "queue_status", ctx.channel.id, msg.id)

        await ctx.send("Queue initialisée et persistée.")

    # ------------------------------------------------
    # Tâche de boucle
    # ------------------------------------------------

    @tasks.loop(seconds=15)
    async def process_queue_task_loop(self):
        """
        Tâche qui tente de former des groupes toutes les 15 secondes.
        Utilise une approche "greedy" pour combiner des blocs.
        """
        async with self.queue_lock():
            entries = await MatchmakingService.get_queue_entries()
            if not entries:
                logger.debug("Queue vide.")
                return

            # On regroupe par (langue, region, platform, team_size)
            grouped = self.group_entries(entries)

            # Ordre de priorité
            # -1 => “N’importe”, on essayera 5,3,2
            team_size_priority = [5, 3, 2, -1]

            for desired_size in team_size_priority:
                for group_key, group_entries in list(grouped.items()):
                    lang, region, platf, tsize = group_key

                    if tsize == -1:
                        # On tente 5,3,2
                        for size in [5, 3, 2]:
                            await self.form_groups_greedy(group_entries, size, group_key)
                    elif tsize == desired_size:
                        await self.form_groups_greedy(group_entries, desired_size, group_key)

                    # Rafraîchir
                    entries = await MatchmakingService.get_queue_entries()
                    grouped = self.group_entries(entries)

    @asynccontextmanager
    async def queue_lock(self):
        async with self.lock:
            yield

    # ------------------------------------------------
    # Groupement par (langue,region,platform,teamsize)
    # ------------------------------------------------

    def group_entries(self, entries: List[Dict]) -> Dict[Tuple[str, str, str, int], List[Dict]]:
        """
        Crée un dict: (langue, region, platform, team_size) -> liste d'entrées
        """
        grouped = {}
        for e in entries:
            # e["langue"], e["region"], e["platform"], e["team_size"]
            k = (e["langue"], e["region"], e["platform"], e["team_size"])
            grouped.setdefault(k, []).append(e)
        return grouped

    # ------------------------------------------------
    # Méthode "greedy" pour former un groupe
    # ------------------------------------------------

    async def form_groups_greedy(self, blocks: List[Dict], desired_size: int, group_key: Tuple[str, str, str, int]):
        """
        Approche “gloutonne” :
         1) Tri des blocks (par ex. par date d'arrivée ou par Elo).
         2) On essaie de piocher des blocks pour atteindre sum(entry_type)=desired_size.
         3) On vérifie l'écart ELO, mmr_extended, rôles.
         4) Si on réussit, on forme un groupe, on le retire de la queue, on met à jour.

        Par défaut, on ne forme qu'un groupe par appel pour éviter trop de complexité.
        """
        if desired_size not in [2, 3, 5]:
            return

        if not blocks:
            return

        # Ex. on trie par timestamp ou Elo.
        # Supposons qu'on trie par 'timestamp' ASC (les plus anciens en premier).
        # Si 'timestamp' n'existe pas dans e, on peut fallback sur un tri par e["elo"] croissant.
        # Ici on fait un tri par date d'insertion (fictive): 
        # blocks sont déjà triés par "ORDER BY timestamp ASC" dans get_queue_entries, 
        # donc on peut s'en passer. 
        # Ou alors:
        # blocks.sort(key=lambda b: b["elo"] or 0)

        # Essayer de former un groupe
        used_blocks = []
        sum_type = 0
        combined_elos = []
        combined_roles = []

        for b in blocks:
            # On regarde si b["entry_type"] + sum_type dépasse desired_size
            if sum_type + b["entry_type"] <= desired_size:
                # On tente d'ajouter ce bloc
                sum_type += b["entry_type"]
                used_blocks.append(b)

                # Ajout ELO
                if b["elo"] is not None:
                    combined_elos.append(b["elo"])

                # Ajout rôles
                combined_roles.extend(b["roles"])

                # Vérifier si on a atteint desired_size
                if sum_type == desired_size:
                    # On check l'écart ELO
                    if combined_elos:
                        elo_high = max(combined_elos)
                        elo_low = min(combined_elos)
                        diff = elo_high - elo_low
                        if diff > 300:
                            # Faut que tous mmr_extended=True
                            if not all(x["mmr_extended"] for x in used_blocks):
                                # On annule => reset
                                logger.debug("diff>300 => mmr_extended=False pour un bloc => on reset.")
                                return
                        # Check rôles (optionnel)
                        unique_roles = set(combined_roles)
                        if len(unique_roles) < desired_size:
                            logger.debug("Plusieurs joueurs ont le même rôle, mais on continue quand même.")
                    else:
                        logger.debug("Aucun ELO => on skip.")
                        return

                    # Tout semble OK => on forme le groupe
                    await self.build_final_group(used_blocks, desired_size)
                    # On arrête après avoir formé un groupe
                    return
            # Sinon, on skip ce bloc et on essaie le suivant
            # => glouton => pas toujours optimal mais O(n).

    async def build_final_group(self, blocks: List[Dict], desired_size: int):
        """
        On a déterminé que 'blocks' forment un groupe de sum(entry_type)=desired_size.
        => Récupérer tous les IDs, create voice, remove from queue, update embed, log...
        """
        all_ids = []
        for b in blocks:
            tmids = b.get("team_member_ids")
            if tmids:
                all_ids.extend(tmids)
            else:
                # solo
                all_ids.append(b["discord_member_id"])
        # unique
        all_ids = list(set(all_ids))

        # Récup discord.Member
        group_members = await MatchmakingService.get_members_from_ids(all_ids)
        if len(group_members) != sum(b["entry_type"] for b in blocks):
            logger.warning("Incohérence: impossible de récupérer le nombre exact de membres.")
            return

        # Crée un salon vocal
        await self.create_voice_channel(group_members)

        # Retire ces blocs de la queue
        for b in blocks:
            tmids = b.get("team_member_ids")
            if tmids:
                await MatchmakingService.remove_players_from_queue(tmids)
            else:
                await MatchmakingService.remove_players_from_queue([b["discord_member_id"]])

        # Update embed (on suppose que tous sont dans la même guilde)
        guild_id = group_members[0].guild.id
        await self.update_queue_status_embed(guild_id)

        logger.info(f"[MATCH] Groupe de {desired_size} formé => {all_ids}")

    # ------------------------------------------------
    # Création du vocal
    # ------------------------------------------------

    async def create_voice_channel(self, group: List[discord.Member]) -> Optional[discord.VoiceChannel]:
        """
        Crée le salon vocal pour ce groupe et envoie l'invite par DM.
        """
        if not group:
            return None
        guild = group[0].guild
        category = discord.utils.get(guild.categories, name="Matchmaking")
        if not category:
            try:
                category = await guild.create_category("Matchmaking")
                logger.info("Catégorie 'Matchmaking' créée.")
            except Exception as e:
                logger.error(f"Erreur create_category: {e}")
                return None

        overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
        for m in group:
            overwrites[m] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)

        try:
            vc_name = "Team-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
            vc = await guild.create_voice_channel(vc_name, category=category, overwrites=overwrites)
            invite = await vc.create_invite(max_uses=len(group), unique=True, reason="Matchmaking formed")

            # Envoi par DM
            for m in group:
                try:
                    await m.send(f"Votre salon vocal: {invite.url}")
                except Exception as e:
                    logger.error(f"Erreur DM {m.display_name}: {e}")

            logger.info(f"Vocal créé: {vc.name}, invite={invite.url}")
            return vc
        except Exception as e:
            logger.error(f"Erreur create_voice_channel: {e}")
            return None

    # ------------------------------------------------
    # Embed: compte solos, teams, total (blocs).
    # ------------------------------------------------

    async def create_queue_embed(self, guild_id: int) -> discord.Embed:
        """
        Construit l'embed principal (version finale) : 
        - solos en attente
        - équipes en attente
        - total blocs dans la queue
        - total équipes créées (self.total_teams_created)
        - rôle prioritaire (self.role_counters => min)
        """
        total_solo = await MatchmakingService.count_solos_in_queue()
        total_team = await MatchmakingService.count_teams_in_queue()
        total_entries = await MatchmakingService.count_total_members_in_queue()

        embed = discord.Embed(
            title="Rejoignez la Queue Valorant",
            description="Choisissez la taille de votre équipe pour rejoindre.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Solos en attente", value=str(total_solo), inline=True)
        embed.add_field(name="Équipes en attente", value=str(total_team), inline=True)
        embed.add_field(name="Entrer total", value=str(total_entries), inline=True)

        # Rôle prioritaire
        if self.role_counters:
            priority_role = min(self.role_counters, key=self.role_counters.get)
            embed.add_field(name="Rôle Prioritaire", value=priority_role.capitalize(), inline=False)
        else:
            embed.add_field(name="Rôle Prioritaire", value="N/A", inline=False)

        embed.set_footer(text="Mise à jour automatique toutes les 15 secondes.")
        return embed

    async def update_queue_status_embed(self, guild_id: int):
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
            logger.info(f"Embed queue mis à jour pour guild={guild_id}.")
        except Exception as e:
            logger.error(f"Erreur update_queue_status_embed guild={guild_id}: {e}")

    # ------------------------------------------------
    # Gestion des Membres & Équipes
    # ------------------------------------------------

    async def remove_from_queue(self, user: discord.Member):
        """
        Retire un joueur/leader de la queue via remove_player_from_queue.
        """
        async with self.queue_lock():
            removed = await MatchmakingService.remove_player_from_queue(user.id)
            if not removed:
                raise ValueError("Vous n'êtes pas dans la queue.")
            await self.update_queue_status_embed(user.guild.id)
            logger.info(f"{user.display_name} retiré de la queue.")

    async def handle_team_member_leave(self, member: discord.Member):
        """
        Si un member est leader d'une team, on retire la team entière.
        """
        async with self.queue_lock():
            team_code = await MatchmakingService.is_user_leader_of_team(member.id)
            if team_code:
                team_members = await MatchmakingService.get_team_members(team_code)
                await MatchmakingService.remove_players_from_queue(team_members)
                await self.update_queue_status_embed(member.guild.id)
                logger.info(f"Équipe {team_code} retirée suite au départ de {member.display_name}.")

    # ------------------------------------------------
    # Exemples de fonctions d'ajout en queue
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
    ):
        async with self.queue_lock():
            # Vérif si user est déjà leader d'une team
            if await MatchmakingService.is_user_leader_of_team(user.id):
                raise ValueError("Déjà leader d'une équipe, impossible de rejoindre en solo.")
            
            # On insère la nouvelle entrée
            await MatchmakingService.add_entry_to_queue(
                entry_type=1,  # solo
                discord_member_id=user.id,
                team_member_ids=None,
                langue=langue,
                region=region,
                platform=platform,
                team_size=team_size,
                mmr_extended=mmr_extended,
                elo=elo,
                elo_high=elo,  # pour un solo, elo_high = elo
                elo_low=elo,   # idem
                roles=roles
            )

            # **Incrémenter** nos compteurs pour chaque rôle présent dans `roles`
            for r in roles:
                if r in self.role_counters:
                    self.role_counters[r] += 1

            # On met à jour l'embed
            await self.update_queue_status_embed(user.guild.id)
            logger.info(f"[Queue] Solo ajouté => {user.display_name}, rôles={roles}")

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
    ):
        """
        Ajoute un groupe partiel => entry_type = len(members) (2..4) + team_member_ids=[...].
        """
        async with self.queue_lock():
            for m in members:
                if await MatchmakingService.is_user_leader_of_team(m.id):
                    raise ValueError(f"{m.display_name} déjà leader d'une autre équipe.")

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
            logger.info(f"[Queue] Groupe partiel (size={entry_type}) ajouté => leader={leader.display_name}")

    async def add_preformed_team_to_queue(
        self,
        leader: discord.Member,
        desired_size: int,      # 2,3,5, ou 0 (“n’importe”)
        mmr_extended: bool,
        langue: str,
        region: str,
        platform: str,
        roles: List[str]
    ):
        """
        Ajoute une équipe préformée dans la queue, à condition que 'leader' 
        soit vraiment le leader d'une équipe dans la table 'teams'.

        Étapes :
        1) Vérifie que l'utilisateur est leader d'une équipe (table 'teams').
        2) Récupère tous les membres via get_team_members().
        3) Calcule ELO moyen, ELO high, ELO low (pour l'ensemble des membres).
        4) Fait une union de leurs rôles (optionnel : tu peux réutiliser 'roles' passés en param).
        5) Appelle add_entry_to_queue(...) pour insérer le bloc dans 'matchmaking_queue'.
        """
        # 1) Vérifier le leadership
        code = await MatchmakingService.is_user_leader_of_team(leader.id)
        if not code:
            raise ValueError("Vous n'êtes pas le leader d'une équipe.")

        # 2) Récupérer tous les membres
        member_ids = await MatchmakingService.get_team_members(code)
        if not member_ids:
            raise ValueError("Votre équipe est vide. Impossible de rejoindre la queue.")

        # 3) Calcul de l'ELO moyen, min, max
        total_elo = 0
        elo_high = -999999
        elo_low = 999999
        valid_members = []
        for mid in member_ids:
            user_info = await MatchmakingService.get_user_info(mid)
            if not user_info:
                raise ValueError(f"Le membre {mid} n'a pas d'information Valorant. Impossible d'ajouter.")
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

        # 4) Union des rôles si tu veux être plus précis.
        #    Ici, on réutilise 'roles' passé en param, 
        #    mais tu pourrais itérer sur chaque membre pour union plus fine.
        #    Par ex.:
        # union_roles = set(roles)  # de base
        # for mid in valid_members:
        #    => get user roles ?

        # Au final, on va insérer un 'entry_type' = taille du groupe (2..5).
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

        # Incrémenter les compteurs pour tous les rôles dans 'roles'.
        for r in roles:
            if r in self.role_counters:
                self.role_counters[r] += 1

        # Update embed
        guild_id = leader.guild.id
        await self.update_queue_status_embed(guild_id)
        self.bot.logger.info(
            f"[Queue] Team ajoutée => leader={leader.display_name}, roles={roles}"
        )

        logger.info(
            f"[Queue] Équipe '{code}' (leader={leader.display_name}) ajoutée en queue : "
            f"entry_type={entry_type}, desired_size={desired_size}, mmr_extended={mmr_extended}, "
            f"elo_moy={elo_moy}, elo_high={elo_high}, elo_low={elo_low}, roles={roles}."
        )



# ------------------------------------------------
# Setup du cog
# ------------------------------------------------

async def setup(bot: commands.Bot):
    await bot.add_cog(MatchmakingQueue(bot))
    logger.info("MatchmakingQueue chargé.")
