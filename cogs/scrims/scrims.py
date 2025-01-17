import logging
import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta

from cogs.scrims.service.scrims_services import ScrimService

logger = logging.getLogger("scrims")

class ScrimCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service = ScrimService()
        # Lancement des tâches asynchrones au démarrage
        asyncio.create_task(self.load_persistent_messages())
        asyncio.create_task(self.load_active_scrims())
        asyncio.create_task(self.scrim_end_checker())

    @commands.command(name="init_scrim")
    async def init_scrim(self, ctx: commands.Context):
        """
        Envoie le message principal contenant le bouton "Créer un scrim" et le persiste.
        """
        view = discord.ui.View()
        view.add_item(CreateScrimButton(self.bot))
        message = await ctx.send("Cliquez sur le bouton ci-dessous pour créer un scrim :", view=view)
        internal_guild_id = await self.service.get_internal_server_id(ctx.guild.id)
        if internal_guild_id is not None:
            await self.service.persist_message(
                channel_id=message.channel.id,
                message_id=message.id,
                message_type="scrim_creation",
                guild_id=internal_guild_id
            )

    async def load_persistent_messages(self):
        """
        Au démarrage, pour chaque guilde, charge le message persistant principal et y ré-attache la vue.
        """
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            internal_guild_id = await self.service.get_internal_server_id(guild.id)
            if internal_guild_id is None:
                logger.warning(f"Serveur introuvable en BDD pour la guilde {guild.id}.")
                continue
            data = await self.service.get_persistent_messages("scrim_creation", internal_guild_id)
            if data:
                msg_data = data[0]  # utilisation du premier message persistant
                channel = guild.get_channel(msg_data.get("channel_id"))
                if channel:
                    try:
                        message = await channel.fetch_message(msg_data.get("message_id"))
                        view = discord.ui.View()
                        view.add_item(CreateScrimButton(self.bot))
                        await message.edit(view=view)
                        logger.info(f"CreateScrimButton réassigné pour guild (ID interne={internal_guild_id}).")
                    except Exception as e:
                        logger.error(f"Erreur lors de la réassignation du CreateScrimButton: {e}")
            else:
                logger.warning(f"Aucun message persistant de création de scrim trouvé pour la guilde (ID interne={internal_guild_id}).")

    async def load_active_scrims(self):
        """
        Au démarrage, recharge et ré-attache la vue pour chaque embed de scrim actif.
        Ceci permet de lier correctement les boutons au scrim correspondant,
        même après un redémarrage du bot.
        """
        await self.bot.wait_until_ready()
        active_scrims = await self.service.get_active_scrims()  # Retourne id, message_id, channel_id, etc.
        if not active_scrims:
            logger.info("Aucun scrim actif trouvé.")
            return

        for scrim in active_scrims:
            scrim_id = scrim.get("id")
            channel_id = scrim.get("channel_id")
            message_id = scrim.get("message_id")
            if not all([scrim_id, channel_id, message_id]):
                continue
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.warning(f"Channel {channel_id} introuvable pour scrim {scrim_id}.")
                continue
            try:
                message = await channel.fetch_message(message_id)
            except Exception as e:
                logger.error(f"Erreur lors de la récupération du message {message_id} pour scrim {scrim_id}: {e}")
                continue
            view = ScrimView(scrim_id, cog=self)
            try:
                await message.edit(view=view)
                logger.info(f"Vue ré-attachée pour scrim {scrim_id}.")
            except Exception as e:
                logger.error(f"Erreur lors de la ré-attache de la vue pour scrim {scrim_id}: {e}")

    async def scrim_end_checker(self):
        """
        Vérifie périodiquement (toutes les minutes) si des scrims actifs sont arrivés à échéance,
        et déclenche leur traitement de fin.
        """
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                active_scrims = await self.service.get_active_scrims_full_info()
                now = datetime.now()
                for scrim in active_scrims:
                    scrim_id = scrim.get("id")
                    scrim_datetime = scrim.get("datetime")
                    if not scrim_datetime:
                        continue
                    # Si l'heure du scrim est passée depuis au moins 60 secondes
                    if now >= scrim_datetime + timedelta(seconds=60):
                        logger.info("Le scrim %s est arrivé à échéance (prévu pour %s)", scrim_id, scrim_datetime)
                        asyncio.create_task(self.schedule_scrim_end(scrim_id, scrim_datetime))
                await asyncio.sleep(60)
            except Exception as e:
                logger.error("Erreur dans scrim_end_checker: %s", e)
                await asyncio.sleep(60)

    async def build_scrim_embed(self, scrim_info: dict, creator_name: str) -> discord.Embed:
        """
        Construit l'embed de présentation du scrim.
        Le titre affiche le nombre de participants inscrits sur le total (ici, 10).
        """
        total_max = 10
        nb_inscrits = scrim_info.get("nb_participants", 0)
        titre = f"Scrim de {creator_name} {nb_inscrits}/{total_max}"
        embed = discord.Embed(title=titre, color=discord.Color.blue())

        date_obj = scrim_info.get("datetime")
        date_str = date_obj.strftime("%d/%m/%Y") if date_obj else "-"
        heure_str = date_obj.strftime("%H:%M") if date_obj else "-"

        embed.add_field(name="🗺 Map", value=scrim_info.get("map", "-"), inline=True)
        embed.add_field(name="🥇 Rang", value=scrim_info.get("rang", "-"), inline=True)
        embed.add_field(name="📅 Date et Heure", value=f"{date_str} à {heure_str}", inline=True)
        if scrim_info.get("autre"):
            embed.add_field(name="📰 Autres précisions", value=scrim_info.get("autre"), inline=False)

        team1 = await self.format_team(scrim_info.get("team1", []))
        team2 = await self.format_team(scrim_info.get("team2", []))
        embed.add_field(name="Équipe 1", value=team1, inline=True)
        embed.add_field(name="Équipe 2", value=team2, inline=True)
        return embed

    async def format_team(self, team: list) -> str:
        mentions = []
        for internal_id in team:
            discord_id = await self.service.get_discord_id(internal_id)
            if discord_id:
                mentions.append(f"<@{discord_id}>")
            else:
                mentions.append("Inconnu")
        return ", ".join(mentions) if mentions else "En attente..."

    async def schedule_scrim_end(self, scrim_id: int, scrim_datetime: datetime):
        """
        Traite la fin du scrim : supprime l'embed, supprime le scrim en BDD et envoie un rappel en MP aux participants.
        """
        now = datetime.now()
        delay = (scrim_datetime - now).total_seconds()
        if delay < 0:
            delay = 0
        await asyncio.sleep(delay)
        logger.info("Début du traitement de fin de scrim %s", scrim_id)

        scrim_info = await self.service.get_scrim_info(scrim_id)
        if not scrim_info:
            logger.error("Scrim %s non trouvé en BDD", scrim_id)
            return

        participants = await self.service.get_scrim_participants(scrim_id)
        if not participants:
            logger.info("Aucun participant trouvé pour le scrim %s", scrim_id)

        channel = self.bot.get_channel(scrim_info.get("channel_id"))
        if channel:
            try:
                message = await channel.fetch_message(scrim_info.get("message_id"))
                await message.delete()
                logger.info("Message d'embed du scrim %s supprimé", scrim_id)
            except Exception as e:
                logger.error("Erreur lors de la suppression de l'embed du scrim %s: %s", scrim_id, e)
        else:
            logger.warning("Channel non trouvé pour scrim %s", scrim_id)

        await self.service.delete_scrim(scrim_id)

        # Envoi d'un rappel par MP aux participants
        for internal_user_id in participants:
            discord_id = await self.service.get_discord_id(internal_user_id)
            if discord_id:
                user = self.bot.get_user(discord_id)
                if not user:
                    try:
                        user = await self.bot.fetch_user(discord_id)
                    except Exception as fetch_err:
                        logger.error("Erreur lors de la récupération de l'utilisateur %s: %s", discord_id, fetch_err)
                        continue
                try:
                    await user.send("Rappel : Le scrim auquel vous étiez inscrit vient de débuter !")
                    logger.info("Rappel envoyé à l'utilisateur %s", discord_id)
                except Exception as e:
                    logger.error("Erreur lors de l'envoi du DM à l'utilisateur %s: %s", discord_id, e)
            else:
                logger.warning("Impossible de retrouver le discord_id pour l'utilisateur interne %s", internal_user_id)

# ---- Vues et interactions ----

class CreateScrimButton(discord.ui.Button):
    def __init__(self, bot: commands.Bot):
        super().__init__(label="Créer un scrim", style=discord.ButtonStyle.primary, custom_id="create_scrim")
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ScrimModal(self.bot))

class ScrimModal(discord.ui.Modal, title="Créer un scrim"):
    date = discord.ui.TextInput(
        label="Date (JJ/MM/YYYY)",
        placeholder="Ex : 25/12/2025",
        required=True
    )
    heure = discord.ui.TextInput(
        label="Heure (HH:MM)",
        placeholder="Ex : 20:00",
        required=True
    )
    map = discord.ui.TextInput(
        label="Map",
        placeholder="Nom de la map",
        required=True
    )
    rang = discord.ui.TextInput(
        label="Rang",
        placeholder="Ex : Bronze, Argent, Or...",
        required=True
    )
    autres_precision = discord.ui.TextInput(
        label="Autres précisions",
        placeholder="Informations supplémentaires",
        style=discord.TextStyle.paragraph,
        required=False
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.service = ScrimService()

    async def on_submit(self, interaction: discord.Interaction):
        try:
            scrim_datetime = datetime.strptime(f"{self.date.value} {self.heure.value}", "%d/%m/%Y %H:%M")
        except ValueError:
            return await interaction.response.send_message("Format de date ou d'heure invalide.", ephemeral=True)

        channel_id = interaction.channel.id
        internal_guild_id = await self.service.get_internal_server_id(interaction.guild.id)
        if internal_guild_id is None:
            return await interaction.response.send_message("Le serveur n'est pas enregistré en BDD.", ephemeral=True)

        creator_discord_id = interaction.user.id
        internal_user_id = await self.service.get_internal_user_id(creator_discord_id)
        if internal_user_id is None:
            return await interaction.response.send_message("Vous n'êtes pas enregistré dans la BDD.", ephemeral=True)

        scrim_id = await self.service.create_scrim(
            scrim_datetime=scrim_datetime,
            map_name=self.map.value,
            rang=self.rang.value,
            autre=self.autres_precision.value,
            initial_participants=[internal_user_id],
            message_id=0,  # Mise à jour ultérieure
            channel_id=channel_id,
            guild_id=internal_guild_id
        )
        if scrim_id is None:
            return await interaction.response.send_message("Erreur lors de la création du scrim.", ephemeral=True)

        scrim_info = await self.service.update_scrim_embed_info(scrim_id)
        if scrim_info:
            scrim_info["scrim_id"] = scrim_id
        creator_name = interaction.user.name

        # Création de l'embed et de la vue pour le scrim
        cog_instance = self.bot.get_cog("ScrimCog")
        embed = await cog_instance.build_scrim_embed(scrim_info, creator_name)
        view = ScrimView(scrim_id, cog=cog_instance)
        scrim_message = await interaction.channel.send(embed=embed, view=view)
        await self.service.update_scrim_message(scrim_id, scrim_message.id)

        # Planifier le traitement de fin du scrim dès que l'heure arrive
        asyncio.create_task(cog_instance.schedule_scrim_end(scrim_id, scrim_datetime))
                
        await interaction.response.send_message("Scrim créé avec succès !", ephemeral=True)

class ScrimView(discord.ui.View):
    def __init__(self, scrim_id: int, cog):
        super().__init__(timeout=None)
        self.scrim_id = scrim_id
        self.cog = cog

    @discord.ui.button(label="Rejoindre le scrim", style=discord.ButtonStyle.success, custom_id="join_scrim")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Utilisation de l'instance de service partagée dans le cog
        service = self.cog.service
        internal_user_id = await service.get_internal_user_id(interaction.user.id)
        if internal_user_id is None:
            return await interaction.response.send_message("Vous n'êtes pas enregistré en BDD.", ephemeral=True)
        if await service.is_user_registered(self.scrim_id, internal_user_id):
            return await interaction.response.send_message("Vous êtes déjà inscrit.", ephemeral=True)
        if not await service.add_participant(self.scrim_id, internal_user_id):
            return await interaction.response.send_message("Erreur lors de l'inscription.", ephemeral=True)

        new_info = await service.update_scrim_embed_info(self.scrim_id)
        if new_info is not None:
            # Récupération du nom du créateur
            creator_name = new_info.get("creator_name", interaction.user.name)
            new_embed = await self.cog.build_scrim_embed(new_info, creator_name)
            await interaction.message.edit(embed=new_embed, view=self)
        await interaction.response.send_message("Inscription validée !", ephemeral=True)

    @discord.ui.button(label="Quitter le scrim", style=discord.ButtonStyle.danger, custom_id="leave_scrim")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        service = self.cog.service
        internal_user_id = await service.get_internal_user_id(interaction.user.id)
        if internal_user_id is None:
            return await interaction.response.send_message("Vous n'êtes pas reconnu dans la BDD.", ephemeral=True)
        if not await service.is_user_registered(self.scrim_id, internal_user_id):
            return await interaction.response.send_message("Vous n'êtes pas inscrit.", ephemeral=True)
        if not await service.remove_participant(self.scrim_id, internal_user_id):
            return await interaction.response.send_message("Erreur lors de la désinscription.", ephemeral=True)
        
        new_info = await service.update_scrim_embed_info(self.scrim_id)
        if new_info is not None:
            creator_name = new_info.get("creator_name", interaction.user.name)
            new_embed = await self.cog.build_scrim_embed(new_info, creator_name)
            await interaction.message.edit(embed=new_embed, view=self)
        await interaction.response.send_message("Vous avez quitté le scrim.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ScrimCog(bot))
    logger.info("ScrimCog chargé.")
