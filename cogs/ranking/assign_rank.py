# cogs/ranking/assign_rank.py

import discord
from discord.ext import commands, tasks
from cogs.ranking.services.assign_rank_service import (
    store_persistent_message,
    get_persistent_message,
    get_channel_id,
    update_user_valorant_info,
    set_valorant_details,
    get_all_users_with_valo_info,
    get_role_mappings,
    refresh_role_mappings
)
from cogs.ranking.services.valorant_service import get_puuid, get_player_rank
from utils.database import database
import logging
import asyncio

logger = logging.getLogger("embed_cog")

# --- NOUVEAU : Dictionnaire rang Valorant → ID dans roles_configurations ---
VALORANT_RANK_TO_DB_ID = {
    "Iron 1": 3,
    "Iron 2": 3,
    "Iron 3": 3,
    "Bronze 1": 4,
    "Bronze 2": 4,
    "Bronze 3": 4,
    "Silver 1": 5,
    "Silver 2": 5,
    "Silver 3": 5,
    "Gold 1": 6,
    "Gold 2": 6,
    "Gold 3": 6,
    "Platinum 1": 7,
    "Platinum 2": 7,
    "Platinum 3": 7,
    "Diamond 1": 8,
    "Diamond 2": 8,
    "Diamond 3": 8,
    "Ascendant 1": 9,
    "Ascendant 2": 9,
    "Ascendant 3": 9,
    "Immortal 1": 10,
    "Immortal 2": 10,
    "Immortal 3": 10,
    "Radiant": 11,
    "no_rank": 41,
}

# Type de message persistant
EMBED_MESSAGE_TYPE = "embed_selection"

class PseudoTagModal(discord.ui.Modal, title="Renseignez votre Pseudo et Tag Valorant"):
    pseudo = discord.ui.TextInput(
        label="Pseudo",
        placeholder="Entrez votre pseudo Valorant",
        max_length=16,
        required=True,
    )
    tag = discord.ui.TextInput(
        label="Tag",
        placeholder="Entrez votre tag Valorant",
        max_length=6,
        required=True,
    )

    def __init__(self, user: discord.User):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        pseudo = self.pseudo.value.strip()
        tag = self.tag.value.strip()

        # Validation des entrées
        if not pseudo.isalnum():
            await interaction.response.send_message(
                "Le pseudo ne doit contenir que des lettres et des chiffres.", ephemeral=True
            )
            return

        if not tag.isalnum():
            await interaction.response.send_message(
                "Le tag ne doit contenir que des lettres et des chiffres.", ephemeral=True
            )
            return

        try:
            success = await update_user_valorant_info(interaction.user.id, pseudo, tag)
            if success:
                await interaction.response.send_message(
                    f"Vos informations Valorant ont été enregistrées : {pseudo}#{tag}", 
                    ephemeral=True
                )
                logger.info(
                    f"Utilisateur {interaction.user} a enregistré son pseudo et tag Valorant."
                )
            else:
                await interaction.response.send_message(
                    "Une erreur est survenue lors de l'enregistrement de vos informations. "
                    "Veuillez réessayer plus tard.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement des données pour {interaction.user}: {e}")
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'enregistrement de vos informations. "
                "Veuillez réessayer plus tard.",
                ephemeral=True
            )

class EmbedButtonsView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)  # Garder la vue active indéfiniment
        self.cog = cog

    @discord.ui.button(label="Renseigner Pseudo et Tag", style=discord.ButtonStyle.primary, custom_id="button:pseudo_tag")
    async def pseudo_tag_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PseudoTagModal(interaction.user)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Deuxième Bouton", style=discord.ButtonStyle.secondary, custom_id="button:second")
    async def second_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Fonctionnalité pour le deuxième bouton (exemple)
        await interaction.response.send_message("Deuxième bouton cliqué !", ephemeral=True)

class EmbedCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.message_id = None
        logger.info("EmbedCog initialisé.")
        self.bot.loop.create_task(self.reload_persistent_embed())
        self.update_roles_task.start()
        self.refresh_roles_cache_task.start()

    def cog_unload(self):
        self.update_roles_task.cancel()
        self.refresh_roles_cache_task.cancel()

    async def reload_persistent_embed(self):
        await self.bot.wait_until_ready()
        logger.info("Rechargement de l'embed persistant...")

        for guild in self.bot.guilds:
            message_data = await get_persistent_message(guild.id, EMBED_MESSAGE_TYPE)
            if not message_data:
                logger.info(f"Aucun message persistant trouvé pour la guilde {guild.id}.")
                continue

            channel = guild.get_channel(message_data["channel_id"])
            if not channel:
                logger.warning(f"Canal introuvable : {message_data['channel_id']} dans guild_id={guild.id}")
                continue

            try:
                message = await channel.fetch_message(message_data["message_id"])
                view = EmbedButtonsView(self)
                self.bot.add_view(view, message_id=message.id)
                logger.info(f"Vue ajoutée pour le message {message.id} dans le canal {channel.name}")
            except discord.NotFound:
                logger.warning(f"Message introuvable : {message_data['message_id']} dans le canal {channel.name}")
            except Exception as e:
                logger.error(f"Erreur lors du rechargement de l'embed persistant : {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f"Cog {self.__class__.__name__} prêt.")

    @commands.command(name="send_embed")
    @commands.has_permissions(administrator=True)
    async def send_embed(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        action = "rang"

        channel_id = await get_channel_id(guild_id, action)
        if not channel_id:
            await ctx.send(f"Aucun salon défini pour l'action '{action}'.", delete_after=10)
            logger.error(f"Aucun salon défini pour l'action '{action}' dans guild_id={guild_id}.")
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send("Le salon d'embed spécifié est introuvable.", delete_after=10)
            logger.error(f"Salon d'embed introuvable : {channel_id} dans guild_id={guild_id}.")
            return

        # Vérifie si l'embed a déjà été envoyé
        message_data = await get_persistent_message(guild_id, EMBED_MESSAGE_TYPE)
        if message_data:
            try:
                message = await channel.fetch_message(message_data["message_id"])
                await ctx.send("L'embed a déjà été envoyé dans ce salon.", delete_after=10)
                logger.info(f"L'embed existe déjà avec le message ID {message.id} dans guild_id={guild_id}.")
                return
            except discord.NotFound:
                logger.warning(f"Message persistant introuvable : {message_data['message_id']} dans {channel.name}. Envoi d'un nouvel embed.")

        embed = discord.Embed(
            title="Bienvenue !",
            description="Cliquez sur les boutons ci-dessous pour interagir.",
            color=discord.Color.blue()
        )
        view = EmbedButtonsView(self)
        try:
            message = await channel.send(embed=embed, view=view)
            success = await store_persistent_message(guild_id, channel.id, message.id, EMBED_MESSAGE_TYPE)
            if success:
                await ctx.send(f"Embed envoyé dans {channel.mention}.", delete_after=10)
                logger.info(f"Embed envoyé dans le salon {channel.id} par {ctx.author} et stocké en base de données.")
            else:
                await ctx.send("Embed envoyé, mais une erreur est survenue lors du stockage en base de données.", delete_after=10)
                logger.error("Embed envoyé, mais échec du stockage en base de données.")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi de l'embed : {e}")
            await ctx.send("Une erreur est survenue lors de l'envoi de l'embed.", delete_after=10)

    @send_embed.error
    async def send_embed_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Tu n'as pas la permission d'utiliser cette commande.", delete_after=10)
        else:
            logger.error(f"Erreur dans send_embed: {error}")
            await ctx.send("Une erreur est survenue lors de l'exécution de la commande.", delete_after=10)

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context):
        await ctx.send("Pong!")

    # --- Tâche de mise à jour toutes les 30 minutes ---
    @tasks.loop(minutes=30)
    async def update_roles_task(self):
        logger.info("Début de la tâche de mise à jour des rôles Valorant.")

        # 1) Récupération de tous les utilisateurs
        users = await get_all_users_with_valo_info()
        logger.info(f"{len(users)} utilisateurs trouvés pour la mise à jour des rôles.")

        # ========================================================================
        # EXEMPLE D'IDÉE POUR LA MISE À JOUR PAR LOTS (CHUNKS)
        # ------------------------------------------------------------------------
        # Vous pouvez décommenter si vous avez > 100 utilisateurs ou pour limiter
        # le temps par "boucle". Par exemple, traiter 20 utilisateurs à la fois.
        #
        # def chunkify(iterable, size):
        #     for i in range(0, len(iterable), size):
        #         yield iterable[i:i+size]
        #
        # for chunk in chunkify(users, 20):
        #     # Traiter le lot de 20 users ici
        #     for record in chunk:
        #         ... votre logique ...
        #     # Optionnel: un petit sleep pour éviter de saturer l'API
        #     await asyncio.sleep(2)
        #
        # ------------------------------------------------------------------------
        # Si vous laissez tel quel, on traite tout séquentiellement dans un seul for.
        # ========================================================================

        for record in users:
            discord_id   = record["discord_id"]
            pseudo       = record["valorant_pseudo"]
            tag          = record["valorant_tag"]
            puuid        = record.get("valorant_puuid")
            region       = record.get("valorant_region")
            current_rank = record.get("valorant_rank")
            current_elo  = record.get("valorant_elo")

            # --- Récupération du "member" Discord ---
            member = None
            for guild in self.bot.guilds:
                m = guild.get_member(discord_id)
                if m:
                    member = m
                    break
            if not member:
                logger.warning(f"[update_roles_task] Member introuvable pour Discord ID {discord_id}.")
                continue

            # --- 1) Vérifier/récupérer puuid et region si manquants ---
            if not puuid or not region:
                valo_info = await get_puuid(pseudo, tag)
                if valo_info:
                    nom_tag, region, puuid = valo_info
                    success = await set_valorant_details(discord_id, puuid, region, current_rank, current_elo)
                    if success:
                        logger.info(f"[update_roles_task] PUUID et région mis à jour pour Discord ID {discord_id}.")
                else:
                    logger.warning(f"[update_roles_task] Impossible de récupérer le PUUID pour {pseudo}#{tag}.")
                    continue

            # --- 2) Récupérer le rang du joueur via l'API ---
            stats = await get_player_rank(region, puuid)
            if stats:
                new_rank, new_elo = stats
            else:
                # 404 ou autre => pas de rang compétitif
                new_rank, new_elo = None, None
                logger.info(f"[update_roles_task] Joueur {pseudo}#{tag} n'a pas de rang compétitif (ou échec API).")

            # --- 3) Mettre à jour la DB si rang/Elo ont changé ---
            if (new_rank != current_rank) or (new_elo != current_elo):
                if new_rank and new_elo:
                    success = await set_valorant_details(discord_id, puuid, region, new_rank, new_elo)
                    if success:
                        logger.info(f"[update_roles_task] Rang/Elo mis à jour pour {discord_id}: {new_rank}, Elo={new_elo}")
                else:
                    # Joueur pas classé => on n'update pas ou on met "no_rank" si vous le souhaitez
                    pass

            # --- 4) Déterminer le nouveau rôle "rang Valorant" à attribuer ---
            guild_id = member.guild.id
            if not new_rank:
                # Vous pouvez gérer ici un rôle "no_rank" si vous le souhaitez.
                continue
            else:
                role_config_id = VALORANT_RANK_TO_DB_ID.get(new_rank)
                if not role_config_id:
                    logger.warning(f"[update_roles_task] Aucun mapping pour le rang {new_rank} dans VALORANT_RANK_TO_DB_ID.")
                    continue

            # --- 5) On va chercher en base le role_id Discord lié à role_config_id ---
            query = """
                SELECT role_id
                FROM roles_configurations
                WHERE guild_id = $1
                AND id = $2
            """
            discord_role_id = await database.fetchval(query, guild_id, role_config_id)
            if not discord_role_id:
                logger.warning(f"[update_roles_task] Aucun 'role_id' trouvé en base pour guild={guild_id}, id={role_config_id}.")
                continue

            desired_role = member.guild.get_role(discord_role_id)
            if not desired_role:
                logger.warning(f"[update_roles_task] Rôle introuvable sur le serveur : {discord_role_id}")
                continue

            # --- 6) Supprimer les anciens rôles de rang, laisser les autres intactes ---
            # On récupère tous les role_id "Valorant" pour cette guilde :
            role_mappings = await get_role_mappings(guild_id)
            if not role_mappings:
                logger.warning(f"[update_roles_task] Aucun mapping de rôles trouvé pour guild_id={guild_id}.")
                continue

            # role_mappings est un dict { role_name: <discord_role_id> }
            # Pour ne retirer que les rôles Valorant, on prend la liste des IDs
            rank_role_ids = set(role_mappings.values())

            roles_to_remove = []
            for r in member.roles:
                # Si c'est un rôle "rang Valorant" ET qu'il est différent du nouveau
                if r.id in rank_role_ids and r.id != desired_role.id:
                    roles_to_remove.append(r)

            if roles_to_remove:
                try:
                    await member.remove_roles(*roles_to_remove, reason="Mise à jour du rang Valorant")
                    logger.info(f"[update_roles_task] Rôles supprimés pour {member.display_name}: {[r.name for r in roles_to_remove]}")
                except Exception as e:
                    logger.error(f"[update_roles_task] Erreur lors de la suppression de rôles pour {member.display_name}: {e}")
                    continue

            # --- 7) Ajouter le nouveau rôle de rang si le membre ne l'a pas déjà ---
            if desired_role not in member.roles:
                try:
                    await member.add_roles(desired_role, reason="Mise à jour du rang Valorant")
                    logger.info(f"[update_roles_task] Rôle '{desired_role.name}' ajouté à {member.display_name}.")
                except Exception as e:
                    logger.error(f"[update_roles_task] Erreur lors de l'ajout du rôle '{desired_role.name}' à {member.display_name}: {e}")

        logger.info("Fin de la tâche de mise à jour des rôles Valorant.")

    # --- Tâche de rafraîchissement du cache (inchangé) ---
    @tasks.loop(hours=1)
    async def refresh_roles_cache_task(self):
        logger.info("Début de la tâche de rafraîchissement du cache des rôles.")
        for guild in self.bot.guilds:
            await refresh_role_mappings(guild.id)
        logger.info("Tâche de rafraîchissement du cache des rôles terminée.")

    @refresh_roles_cache_task.before_loop
    async def before_refresh_roles_cache_task(self):
        await self.bot.wait_until_ready()

    @update_roles_task.before_loop
    async def before_update_roles_task(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedCog(bot))
    logger.info("Cog EmbedCog chargé.")
