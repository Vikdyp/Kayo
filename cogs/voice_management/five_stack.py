# cogs\voice_management\five_stack.py

import discord
from discord.ext import commands, tasks
from typing import List, Optional, Dict, Tuple
from collections import deque
import asyncio
import logging
import datetime

from cogs.voice_management.services.five_stack_service import MatchmakingService
from utils.database import database
from .views import QueueView  # Importer depuis le fichier views.py

logger = logging.getLogger("five_stack")


class Matchmaking(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.main_queue = deque()  # Queue principale mixte (solos et équipes)
        self.queue_status_embed_message = {}  # guild_id: (channel_id, message_id)
        self.last_match_time = {}  # guild_id: datetime of last match formation
        self.MatchmakingService = MatchmakingService

        # Initialiser et démarrer la tâche de traitement de la queue
        self.process_queue_task_loop.start()

    def cog_unload(self):
        self.process_queue_task_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Listener qui s'exécute lorsque le bot est prêt.
        Charge les messages persistants pour les vues de la queue.
        """
        await self.load_persistent_messages()
        logger.info("Matchmaking Cog prêt.")

    async def verify_guilds_and_channels(self):
        for guild in self.bot.guilds:
            logger.info(f"Guild accessible : {guild.name} (ID: {guild.id})")
            for channel in guild.channels:
                if isinstance(channel, discord.TextChannel):
                    logger.info(f"  - Channel : {channel.name} (ID: {channel.id})")

    async def load_persistent_messages(self):
        logger.debug("Début du chargement des messages persistants.")
        try:
            guilds = self.bot.guilds
            for guild in guilds:
                server_id = await MatchmakingService.get_server_id(guild.id)
                if not server_id:
                    logger.warning(f"Serveur non configuré dans la base de données pour guild_id={guild.id}.")
                    continue

                for message_type in ["queue_status"]:
                    result = await MatchmakingService.get_persistent_message(server_id, message_type)
                    if not result:
                        logger.warning(f"Aucun message persistant trouvé pour le type '{message_type}' dans la guilde {guild.id}.")
                        continue

                    channel_id, message_id = result
                    logger.debug(f"Traitement de server_id={server_id}, channel_id={channel_id}, message_id={message_id}")

                    channel = guild.get_channel(channel_id)
                    if not channel:
                        logger.warning(f"Channel introuvable : {channel_id} dans guild {guild.id}")
                        continue

                    try:
                        message = await channel.fetch_message(message_id)
                        logger.debug(f"Message récupéré : {message}")

                        # Associer une nouvelle instance de QueueView au message
                        view = QueueView(self, guild.id)
                        await message.edit(view=view)
                        logger.debug(f"View réassignée au message : {message.id}")
                    except Exception as e:
                        logger.error(f"Erreur lors du chargement du message pour guild_id {guild.id}: {e}")
                        continue

                    self.queue_status_embed_message[guild.id] = (channel_id, message_id)
                    logger.debug(f"Message ajouté à queue_status_embed_message : {self.queue_status_embed_message}")
        except Exception as e:
            logger.error(f"Erreur inattendue dans load_persistent_messages : {e}")

    @commands.command(name="start_queue")
    @commands.has_permissions(administrator=True)
    async def start_queue(self, ctx: commands.Context):
        """
        Initialise et envoie l'embed avec les boutons Solo et Équipe ainsi que le statut de la queue.
        """
        guild_id = ctx.guild.id

        # Récupération de l'ID interne du serveur
        server_id = await MatchmakingService.get_server_id(guild_id)
        if not server_id:
            await ctx.send("Erreur : Serveur non configuré dans la base de données.")
            return
        else:
            logger.info(f"Serveur validé pour guild_id {guild_id}, server_id {server_id}.")

        # Création de l'embed et de la vue
        embed = await self.create_queue_embed(guild_id)
        view = QueueView(self, guild_id)
        message = await ctx.send(embed=embed, view=view)
        logger.info(f"Message envoyé avec succès dans le canal {ctx.channel.id} de la guilde {guild_id}. Message ID : {message.id}.")

        # Sauvegarder le message persistant avec l'ID interne
        try:
            await MatchmakingService.save_persistent_message(server_id, "queue_status", ctx.channel.id, message.id)
            self.queue_status_embed_message[guild_id] = (ctx.channel.id, message.id)
            logger.info(f"Message persistant sauvegardé : server_id={server_id}, message_type='queue_status', channel_id={ctx.channel.id}, message_id={message.id}.")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du message persistant : {e}")
            await ctx.send("Une erreur s'est produite lors de l'enregistrement du message persistant.")

    async def create_voice_channel(self, group: List[discord.Member], embed_channel: discord.TextChannel) -> Optional[discord.VoiceChannel]:
        """
        Crée un salon vocal pour un groupe de joueurs avec des permissions spécifiques,
        et envoie un message avec un lien pour rejoindre le salon.
        """
        try:
            guild = group[0].guild  # Supposons que tous les membres appartiennent à la même guilde
            channel_name = f"Team-{datetime.datetime.utcnow().strftime('%H%M')}"
            
            # Récupérer ou créer une catégorie
            category = discord.utils.get(guild.categories, name="Matchmaking")  # Remplacez par le nom de votre catégorie si nécessaire
            if not category:
                category = await guild.create_category("Matchmaking")

            # Définir les permissions
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),  # Interdit à tous par défaut
            }
            for member in group:
                overwrites[member] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)

            # Créer le salon vocal
            channel = await guild.create_voice_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites
            )

            # Créer un lien d'invitation
            invite = await channel.create_invite(max_uses=5, unique=True)

            # Envoyer le message dans le salon de l'embed
            await embed_channel.send(
                f"Un salon vocal a été créé pour les membres suivants : "
                f"{', '.join(member.mention for member in group)}\n"
                f"Rejoignez le salon : **[{channel.name}]({invite.url})**"
            )

            return channel

        except Exception as e:
            logger.error(f"Erreur lors de la création du salon vocal : {e}")
            return None

    def get_total_players_in_queue(self):
        total_players = 0
        for entry in self.main_queue:
            if entry["type"] == "solo":
                total_players += 1
            elif entry["type"] == "team":
                total_players += len(entry["discord_members"])
        logger.debug(f"Calcul du total des joueurs : {total_players}, Détails de la queue : {list(self.main_queue)}")
        return total_players

    def validate_team_size(self, members: list, required_size: int = 5) -> bool:
        """
        Valide si la liste des membres contient suffisamment de joueurs pour former une équipe complète.
        :param members: Liste des membres à valider.
        :param required_size: Taille minimale requise pour une équipe (par défaut 5).
        :return: True si le groupe est complet, sinon False.
        """
        return len(members) >= required_size

    @tasks.loop(seconds=15)
    async def process_queue_task_loop(self):
        logger.debug("Démarrage de la boucle de traitement de la queue.")
        
        total_players = self.get_total_players_in_queue()
        logger.info(f"Nombre total de joueurs en attente : {total_players}")

        if total_players < 5:
            logger.info(f"Pas assez de membres pour former un groupe (total joueurs : {total_players}).")
            return

        try:
            # Priorité : compléter les équipes existantes
            for entry in list(self.main_queue):
                if entry["type"] == "team" and len(entry["discord_members"]) < 5:
                    remaining_slots = 5 - len(entry["discord_members"])
                    solos = [solo for solo in self.main_queue if solo["type"] == "solo"][:remaining_slots]
                    
                    if len(solos) == remaining_slots:
                        logger.debug(f"Complétage de l'équipe avec {remaining_slots} solos.")
                        # Compléter l'équipe avec des solos
                        for solo in solos:
                            entry["discord_members"].append(solo["discord_member"])
                            entry["roles"].extend(solo["roles"])
                            entry["mmr_low"] = min(entry["mmr_low"], solo["mmr_low"])
                            entry["mmr_high"] = max(entry["mmr_high"], solo["mmr_high"])
                        
                        # Recalcul de mmr_average
                        member_infos = await asyncio.gather(
                            *[MatchmakingService.get_user_info(m.id) for m in entry["discord_members"]]
                        )
                        # Filtrer les résultats None
                        valid_member_infos = [info for info in member_infos if info is not None]
                        
                        if not valid_member_infos:
                            logger.error("Aucune information valide des membres trouvée pour recalculer mmr_average.")
                            continue  # Ou une autre logique de gestion d'erreur

                        entry["mmr_average"] = sum(info["elo"] for info in valid_member_infos) / len(valid_member_infos)
                        logger.debug(f"Nouvelle mmr_average calculée : {entry['mmr_average']}")

                        # Retirer les solos utilisés
                        for solo in solos:
                            self.main_queue.remove(solo)
                            logger.info(f"Solo retiré de la queue : {solo['discord_member'].display_name}")
                        
                        logger.info(f"Équipe complétée : {[member.display_name for member in entry['discord_members']]}")

                        # Créer le salon vocal pour l'équipe complétée
                        group = entry["discord_members"]
                        guild_id = group[0].guild.id
                        embed_channel = self.bot.get_channel(self.queue_status_embed_message[guild_id][0])
                        channel = await self.create_voice_channel(group, embed_channel)
                        if channel:
                            logger.info(f"Salon vocal créé pour l'équipe : {channel}")
                        else:
                            logger.error("Erreur lors de la création du salon vocal.")
                        
                        # Retirer l'équipe complétée de la queue
                        self.main_queue.remove(entry)
                        logger.info(f"Équipe retirée de la queue : {[member.display_name for member in group]}")
                        
                        break  # Sortir de la boucle après avoir complété une équipe

            # Formation d'une nouvelle équipe de 5 si possible
            group = await self.find_matching_group()
            if group and len(group) == 5:
                guild_id = group[0].guild.id
                embed_channel = self.bot.get_channel(self.queue_status_embed_message[guild_id][0])
                channel = await self.create_voice_channel(group, embed_channel)
                if channel:
                    logger.info(f"Salon vocal créé : {channel}")
                else:
                    logger.error("Erreur lors de la création du salon vocal.")
            else:
                logger.info("Aucun groupe complet n'a pu être formé.")

            # Mise à jour de l'embed
            for guild_id in self.queue_status_embed_message.keys():
                await self.update_queue_status_embed(guild_id=guild_id)

        except Exception as e:
            logger.exception(f"Erreur lors du traitement de la queue : {e}")

        logger.debug("Fin de la boucle de traitement.")

    @process_queue_task_loop.before_loop
    async def before_process_queue_task_loop(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)  # Attendre 5 secondes avant de commencer la boucle

    async def create_team(self, leader: discord.User, member_inputs: List[str], server_id: int) -> Tuple[bool, str]:
        logger.debug("Début de la méthode create_team.")
        try:
            guild = leader.guild
            logger.info(f"Création d'équipe initiée par {leader.display_name} avec les membres {member_inputs}.")
            members = []

            # Validation des entrées
            if any(not member_input.strip() for member_input in member_inputs):
                logger.error("Entrée vide détectée dans les membres.")
                return False, "Tous les champs des membres doivent être remplis."

            for idx, member_input in enumerate(member_inputs, start=1):
                logger.debug(f"Traitement du membre {idx}/{len(member_inputs)}: {member_input}")
                try:
                    if member_input.startswith('<@') and member_input.endswith('>'):
                        member_id = int(member_input[2:-1].replace('!', ''))
                    else:
                        member_id = int(member_input)
                    member = guild.get_member(member_id)
                    if not member:
                        return False, f"Le membre {member_input} n'a pas été trouvé."
                    members.append(member)
                except ValueError as e:
                    return False, f"Entrée invalide pour {member_input}."

            # Vérifier les doublons
            if len(set(members)) != len(members):
                return False, "Un membre ne peut pas apparaître plusieurs fois dans l'équipe."

            all_members = [leader] + members
            logger.info(f"Liste complète des membres : {[m.display_name for m in all_members]}.")

            regions, mmrs, roles, languages = set(), [], [], set()
            for member in all_members:
                is_banned = await self.is_user_banned(member, server_id)
                if is_banned:
                    return False, f"{member.display_name} est banni."
                user_info = await MatchmakingService.get_user_info(member.id)
                if not user_info:
                    return False, f"Impossible de récupérer les infos pour {member.display_name}."
                regions.add(user_info["region"])
                mmrs.append(user_info["elo"])
                roles.append(await self.get_user_primary_role(member, server_id))
                language = await self.get_user_language(member, server_id)
                if not language:
                    return False, f"{member.display_name} n'a pas de langue valide."
                languages.add(language)

            # Vérifications des contraintes
            if len(regions) > 1:
                return False, f"Les membres de l'équipe proviennent de régions différentes : {', '.join(regions)}."
            if max(mmrs) - min(mmrs) > 300:
                return False, f"La différence de MMR est trop élevée ({max(mmrs) - min(mmrs)} > 300)."
            if len(languages) > 1:
                return False, f"Langues incompatibles parmi les membres : {', '.join(languages)}."
            if roles.count('fill') > 2:
                return False, "Pas plus de 2 rôles 'fill' par équipe."
            non_fill_roles = [role for role in roles if role != 'fill']
            if len(non_fill_roles) != len(set(non_fill_roles)):
                return False, "Les rôles doivent être uniques, hors 'fill'."

            # Créer et ajouter à la queue
            team_entry = {
                "type": "team",
                "discord_members": all_members,
                "region": list(regions)[0],
                "elo": sum(mmrs) // len(mmrs),
                "mmr_average": sum(mmrs) / len(mmrs),
                "mmr_low": min(mmrs),
                "mmr_high": max(mmrs),
                "roles": roles,
                "language": languages.pop()
            }
            await self.add_to_main_queue(team_entry)
            logger.info("Équipe créée avec succès.")
            return True, "Équipe créée avec succès."

        except Exception as e:
            logger.exception("Erreur inattendue lors de la création de l'équipe.")
            return False, "Erreur inattendue lors de la création de l'équipe."

    async def get_user_primary_role(self, member: discord.Member, server_id: int) -> str:
        """
        Récupère le rôle principal de l'utilisateur (duelist, sentinel, etc.) ou 'fill'.

        Args:
            member (discord.Member): L'utilisateur Discord.
            server_id (int): L'ID du serveur.

        Returns:
            str: Le nom du rôle principal ou 'fill' si aucun rôle spécifique n'est trouvé.
        """
        try:
            role_ids = await MatchmakingService.get_role_ids(server_id)
            for role in member.roles:
                if role.id in role_ids.values():
                    return role.name.lower()
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du rôle principal pour server_id {server_id}: {e}")
        return "fill"

    async def get_user_language(self, member: discord.Member, server_id: int) -> Optional[str]:
        """
        Récupère la langue de l'utilisateur à partir de ses rôles.

        Args:
            member (discord.Member): L'utilisateur Discord.
            server_id (int): L'ID du serveur.

        Returns:
            str: La langue trouvée ou None si aucune langue valide n'est assignée.
        """
        try:
            language_roles = await MatchmakingService.get_language_roles(server_id)
            for lang, role_id in language_roles.items():
                if discord.utils.get(member.roles, id=role_id):
                    return lang
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la langue pour server_id {server_id} : {e}")
        return None

    async def is_user_banned(self, member: discord.Member, server_id: int) -> bool:
        """
        Vérifie si un utilisateur possède le rôle 'ban'.

        Args:
            member (discord.Member): L'utilisateur Discord à vérifier.
            server_id (int): L'ID du serveur.

        Returns:
            bool: True si l'utilisateur est banni, sinon False.
        """
        try:
            ban_role_id = await MatchmakingService.get_role_id(server_id, "ban")
            if not ban_role_id:
                return False
            ban_role = discord.utils.get(member.guild.roles, id=ban_role_id)
            if ban_role and ban_role in member.roles:
                return True
        except Exception as e:
            logger.error(f"Erreur lors de la vérification du rôle 'ban' pour server_id {server_id} : {e}")
        return False

    async def add_to_main_queue(self, entry: Dict):
        # Validation de l'entrée
        if 'type' not in entry or not entry.get('type') in ['solo', 'team']:
            logger.error(f"Entrée invalide ajoutée à la file : {entry}")
            raise KeyError("Champ 'type' manquant ou invalide dans l'entrée.")
        
        # Ajout à la file d'attente
        self.main_queue.append(entry)
        if entry['type'] == 'solo':
            identifier = entry['discord_member'].display_name
        else:
            identifier = ', '.join([m.display_name for m in entry['discord_members']])
        logger.info(f"Entrée ajoutée à la queue : {entry['type']} - {identifier}")
        logger.debug(f"Queue actuelle : {list(self.main_queue)}")

    async def update_queue_status_embed(self, guild_id: int):
        """
        Met à jour l'embed de l'état de la queue dans le message persistant.
        """
        channel_id, message_id = self.queue_status_embed_message.get(guild_id, (None, None))
        if not channel_id or not message_id:
            logger.warning(f"Aucun message persistant trouvé pour guild_id {guild_id}.")
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            logger.error(f"Channel ID {channel_id} introuvable pour guild_id {guild_id}.")
            return

        try:
            message = await channel.fetch_message(message_id)
            embed = await self.create_queue_embed(guild_id)
            view = QueueView(self, guild_id)  # Instancier QueueView depuis views.py
            await message.edit(embed=embed, view=view)
            logger.info(f"Embed de la queue mis à jour pour guild_id {guild_id}.")
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de l'embed de la queue pour guild_id {guild_id} : {e}")

    async def find_matching_group(self) -> Optional[List[discord.Member]]:
        """
        Trouve un groupe de 5 joueurs/équipes compatibles dans la queue principale.
        """
        combined_queue = list(self.main_queue)

        # Filtrer les entrées invalides
        valid_queue = [entry for entry in combined_queue if "mmr_average" in entry and "region" in entry and "language" in entry]

        # Calculer le nombre total de joueurs dans la queue valide
        total_valid_players = sum(1 if entry['type'] == 'solo' else len(entry['discord_members']) for entry in valid_queue)

        logger.info(f"Valid queue after filtering and sorting: {valid_queue}")

        if total_valid_players < 5:
            logger.info(f"Pas assez de membres pour former un groupe (taille actuelle : {total_valid_players}).")
            return None  # Pas assez de joueurs pour former un groupe

        # Trier par MMR
        valid_queue.sort(key=lambda x: x['mmr_average'])
        logger.info(f"Valid queue after filtering and sorting: {valid_queue}")

        for i in range(len(valid_queue)):
            potential_group = []
            total_mmr_low = float('inf')
            total_mmr_high = float('-inf')
            regions = set()
            roles = []
            fill_count = 0
            languages = set()

            total_members = 0  # Suivre le nombre total de membres dans le groupe

            for j in range(i, len(valid_queue)):
                entry = valid_queue[j]
                logger.info(f"Evaluating entry: {entry}")

                # Vérifier la langue
                languages.add(entry['language'])
                if len(languages) > 1:
                    logger.info("Incompatible language detected, breaking.")
                    break

                # Vérifier la région
                regions.add(entry['region'])
                if len(regions) > 1:
                    logger.info("Incompatible region detected, breaking.")
                    break

                # Vérifier le MMR
                total_mmr_low = min(total_mmr_low, entry['mmr_low'])
                total_mmr_high = max(total_mmr_high, entry['mmr_high'])
                if (total_mmr_high - total_mmr_low) > 300:
                    logger.info("MMR range exceeded, breaking.")
                    break

                # Vérifier les rôles
                current_fill = entry['roles'].count('fill')
                if fill_count + current_fill > 2:
                    logger.info("Too many 'fill' roles, breaking.")
                    break
                fill_count += current_fill

                duplicate = False
                for role in entry['roles']:
                    if role != 'fill' and role in roles:
                        duplicate = True
                        break
                    if role != 'fill':
                        roles.append(role)
                if duplicate:
                    logger.info("Duplicate roles detected, breaking.")
                    break

                # Vérifier le nombre total de membres
                num_members = 1 if entry['type'] == 'solo' else len(entry['discord_members'])
                if total_members + num_members > 5:
                    logger.info(f"Adding this entry would exceed 5 members (current: {total_members}, adding: {num_members}). Breaking.")
                    break

                # Ajouter l'entrée au groupe potentiel
                potential_group.append(entry)
                total_members += num_members
                logger.info(f"Potential group so far: {potential_group} with total members: {total_members}")

                if total_members == 5:
                    logger.info("A compatible group of 5 has been found.")
                    break

            if total_members == 5:
                members = []
                for group_entry in potential_group:
                    if group_entry['type'] == 'solo':
                        members.append(group_entry['discord_member'])
                    elif group_entry['type'] == 'team':
                        members.extend(group_entry['discord_members'])

                # Retirer les entrées du groupe de la queue
                for group_entry in potential_group:
                    self.main_queue.remove(group_entry)

                return members

        logger.info("No matching group found.")
        return None

    async def create_queue_embed(self, guild_id: int) -> discord.Embed:
        """
        Crée un embed représentant l'état actuel de la queue.
        """
        queue_language = self.get_queue_language(guild_id)
        solo_count = sum(1 for entry in self.main_queue if entry['type'] == 'solo' and entry['language'] == queue_language)
        team_count = sum(1 for entry in self.main_queue if entry['type'] == 'team' and entry['language'] == queue_language)
        total_members = sum(1 for entry in self.main_queue if entry['type'] == 'solo') + \
                        sum(len(entry['discord_members']) for entry in self.main_queue if entry['type'] == 'team')
        active_groups = 0  # À implémenter selon votre système

        # Calculer le temps d'attente depuis la dernière équipe formée
        last_match = self.last_match_time.get(guild_id)
        if last_match:
            time_since_last_match = datetime.datetime.utcnow() - last_match
            seconds_remaining = 30 - time_since_last_match.total_seconds()
            if seconds_remaining > 0:
                next_match_in = str(datetime.timedelta(seconds=int(seconds_remaining)))
            else:
                next_match_in = "Disponible maintenant"
        else:
            next_match_in = "Disponible maintenant"

        embed = discord.Embed(
            title="Rejoignez la Queue Valorant",
            description="Choisissez votre mode de jeu en cliquant sur un des boutons ci-dessous.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Solo en Attente", value=str(solo_count), inline=True)
        embed.add_field(name="Équipes en Attente", value=str(team_count), inline=True)
        embed.add_field(name="Membres Totaux", value=str(total_members), inline=True)
        embed.add_field(name="Prochain Match", value=next_match_in, inline=True)
        embed.set_footer(text="Mise à jour automatique toutes les 30 secondes.")

        return embed

    def get_queue_language(self, guild_id: int) -> str:
        """
        Détermine la langue de la queue basée sur les membres en attente.
        Si plusieurs langues sont présentes, retourne 'mixte'.
        """
        languages = set()
        for entry in self.main_queue:
            if entry['language']:
                languages.add(entry['language'])
        if len(languages) == 1:
            return languages.pop()
        return "mixte"

    async def setup_voice_view(self, guild_id: int):
        """
        Crée une vue mise à jour pour la queue avec les boutons et les informations.
        """
        embed = await self.create_queue_embed(guild_id)
        view = QueueView(self, guild_id)  # Instancier QueueView depuis views.py
        channel_id, message_id = self.queue_status_embed_message.get(guild_id, (None, None))
        if not channel_id or not message_id:
            logger.warning(f"Aucun message persistant trouvé pour guild_id {guild_id}.")
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            logger.error(f"Channel ID {channel_id} introuvable pour guild_id {guild_id}.")
            return

        try:
            message = await channel.fetch_message(message_id)
            await message.edit(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de la vue pour guild_id {guild_id} : {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Matchmaking(bot))
    logger.info("Matchmaking chargé.")
