import discord
from discord.ext import commands
from cogs.rules.service.rules_services import (
    get_rules_channel_id,
    store_rules_message,
    get_rules_message,
    accept_rules_user
)
import logging

from utils import request_manager

logger = logging.getLogger("rules_cog")

class AcceptRulesView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Accepter le règlement",
        style=discord.ButtonStyle.success,
        custom_id="button:accept_rules"
    )
    async def accept_rules_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1) Défère la réponse
        await interaction.response.defer(ephemeral=True)
        
        # 2) Enfile la requête dans le RequestManager
        await request_manager.enqueue(
            interaction=interaction,
            callback=lambda i: self.cog.do_accept_rules(i),
            request_type="CLASSIC"  # Ou "URGENT" selon la logique
        )

class AcceptRulesCog(commands.Cog):
    """Cog pour gérer l'acceptation des règles via un bouton."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("AcceptRulesCog initialisé.")
        self.bot.loop.create_task(self.reload_persistent_views())

    async def do_accept_rules(self, interaction: discord.Interaction):
        """
        Gère la logique pour accepter les règles.
        """
        try:
            discord_id = interaction.user.id
            success = await accept_rules_user(discord_id)
            if success:
                await interaction.followup.send(
                    "Vous avez accepté le règlement. Bienvenue !",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "Une erreur est survenue lors de l'enregistrement. Veuillez réessayer plus tard.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Erreur lors de l'acceptation des règles pour {interaction.user}: {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors de l'acceptation des règles.",
                ephemeral=True
            )

class RulesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="send_rules")
    @commands.has_permissions(administrator=True)
    async def send_rules_command(self, ctx: commands.Context):
        """
        Envoie l'embed du règlement dans le salon 'rules' 
        et stocke ce message en base (persistent_messages).
        """
        guild = ctx.guild
        guild_id = guild.id
        guild_name = guild.name

        # 1) Récupérer le salon
        channel_id = await get_rules_channel_id(guild_id, guild_name)
        if not channel_id:
            await ctx.send("Aucun salon 'rules' configuré pour cette guilde.", delete_after=10)
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send("Le salon spécifié est introuvable.", delete_after=10)
            return

        # 2) Vérifier s'il y a déjà un message persistant "rules_embed"
        existing_data = await get_rules_message(guild_id, guild_name)
        if existing_data:
            # Tenter de récupérer le message
            try:
                existing_msg = await channel.fetch_message(existing_data["message_id"])
                # Si on arrive ici, c'est qu'il existe déjà
                await ctx.send("Le règlement est déjà envoyé dans ce salon.", delete_after=10)
                return
            except discord.NotFound:
                logger.warning("Le message persistant n'existe plus, on va en recréer un...")

        # 3) Créer l'embed
        embed = discord.Embed(
            title="Règlement du Serveur",
            description=(
                "1. Respect et courtoisie.\n"
                "2. Pas de contenu interdit.\n"
                "3. Le staff a toujours raison :)\n\n"
                "**En cliquant sur 'Accepter le règlement', vous consentez à l'enregistrement de votre Discord ID.**\n"
                "Nous stockons notamment : *votre Discord ID*, et potentiellement vos infos Valorant.\n"
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text="Je vais personnaliser ce règlement plus tard.")

        view = AcceptRulesView()

        # 4) Envoyer l'embed
        message = await channel.send(embed=embed, view=view)

        # 5) Stocker dans persistent_messages
        success = await store_rules_message(guild_id, guild_name, channel_id, message.id)
        if success:
            await ctx.send(f"Règlement envoyé dans {channel.mention}", delete_after=10)
        else:
            await ctx.send(
                "Le règlement a été envoyé, mais une erreur est survenue lors du stockage en base.",
                delete_after=10
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(RulesCog(bot))
    logger.info("RulesCog chargé.")
