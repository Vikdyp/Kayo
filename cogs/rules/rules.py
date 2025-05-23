#cogs/rules/rules.py
import discord
from discord.ext import commands, tasks
import logging

from cogs.rules.service.rules_services import (
    get_rules_channel_id,
    has_accepted_rules,
    store_rules_message,
    get_persistent_message,
    delete_persistent_message,
    accept_rules_user  
)

logger = logging.getLogger("rules")

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
        discord_id = interaction.user.id

        # Vérification si l'utilisateur a déjà accepté le règlement
        already_accepted = await has_accepted_rules(discord_id)
        if already_accepted:
            await interaction.response.send_message(
                "Vous avez déjà accepté le règlement !",
                ephemeral=True
            )
        else:
            success = await accept_rules_user(discord_id)
            if success:
                await interaction.response.send_message(
                    "Vous avez accepté le règlement. Bienvenue !",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "Une erreur est survenue lors de l'enregistrement. Veuillez réessayer plus tard.",
                    ephemeral=True
                )

class RulesCog(commands.Cog):
    """Cog pour gérer les règles avec des boutons persistants."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("RulesCog initialisé.")
        self.bot.loop.create_task(self.reload_persistent_views())

    @commands.command(name="setup_rules")
    @commands.has_permissions(administrator=True)
    async def setup_rules(self, ctx: commands.Context):
        """
        Envoie l'embed du règlement et met à jour le message persistant s'il existe déjà.
        """
        logger.debug("Commande setup_rules exécutée.")
        guild_id = ctx.guild.id
        guild_name = ctx.guild.name
        logger.debug(f"Guild ID: {guild_id}, Guild Name: {guild_name}")

        # Récupérer ou configurer le salon des règles
        channel_id = await get_rules_channel_id(guild_id, guild_name)
        logger.debug(f"Channel ID récupéré: {channel_id}")
        if not channel_id:
            await ctx.send("Aucun salon 'rules' configuré pour cette guilde.", delete_after=10)
            logger.warning("Salon 'rules' non configuré.")
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send("Le salon configuré pour les règles est introuvable.", delete_after=10)
            logger.error("Salon 'rules' introuvable.")
            return

        # Création d'un embed avec des fields pour un affichage optimisé
        embed = discord.Embed(
            title="Règlement du Serveur",
            color=discord.Color.green()
        )
        embed.add_field(
            name="1. Respect et courtoisie",
            value=(
                "> - Traitez **tous les membres** avec respect, quelle que soit leur ancienneté ou statut.\n"
                "> - Faites preuve de politesse, utilisez un langage adapté et évitez les provocations.\n"
                "> - Les propos discriminatoires, haineux, racistes, homophobes, sexistes, etc. sont strictement interdits.\n"
                "> - Gardez un comportement positif et constructif, évitez les conflits inutiles ou provocations.\n"
                "> - **Aucune insulte**, moquerie ou propos agressif ne sera toléré.\n"
                "> - En cas de conflit, contactez un membre du staff plutôt que d'alimenter la tension."
            ),
            inline=False
        )
        embed.add_field(
            name="2. Contenu interdit",
            value=(
                "> - 🚫 **Interdiction stricte de publier du contenu NSFW**, explicite, violent ou choquant.\n"
                "> - Toute forme de **harcèlement**, intimidation ou acharnement sera sévèrement sanctionnée.\n"
                "> - Évitez tout **spam**, flood ou message répétitif pouvant perturber les conversations.\n"
                "> - Signalez tout contenu problématique à un modérateur."
            ),
            inline=False
        )
        embed.add_field(
            name="3. Equipe de modération",
            value=(
                "> - Respectez toujours les décisions prises par l'équipe de modération.\n"
                "> - N'entamez pas de débats publics concernant les décisions du staff.\n"
                "> - En cas de désaccord ou question, contactez poliment un membre du staff en privé.\n"
                "> - Votre coopération avec l'équipe est essentielle pour une bonne ambiance."
            ),
            inline=False
        )
        embed.add_field(
            name="4. Utilisation des salons",
            value=(
                "> - 📌 Chaque salon possède une vocation spécifique ; respectez-les selon leur description respective.\n"
                "> - Évitez les hors-sujets ou l'utilisation abusive des salons dédiés.\n"
                "> - Ne spammez ni en salon vocal ni en salon textuel.\n"
                "> - Suivez les demandes des modérateurs en cas de déplacement de conversation vers un autre salon."
            ),
            inline=False
        )
        embed.add_field(
            name="5. Publicité et promotion",
            value=(
                "> - 📢 Toute publicité non autorisée est strictement interdite.\n"
                "> - Les promotions doivent obligatoirement être validées préalablement par l'administration.\n"
                "> - Envoyez vos demandes de publicité ou partenariat directement à l'administration.\n"
                "> - Les messages promotionnels non autorisés seront supprimés et sanctionnés."
            ),
            inline=False
        )
        avatar_url = self.bot.user.avatar.url if self.bot.user.avatar else None
        embed.set_footer(
            text="En cliquant sur 'Accepter le règlement', vous acceptez les conditions générales d'utilisation.\n\nN'hésite pas à demander de l'aide si tu as des questions !",
            icon_url=avatar_url
        )
        logger.debug("Embed des règles créé.")

        view = AcceptRulesView(self)

        # Vérifier si un message persistant existe déjà et le mettre à jour
        existing_message = await get_persistent_message(guild_id, 'rules_embed', guild_name)
        if existing_message:
            try:
                message = await channel.fetch_message(existing_message["message_id"])
                await message.edit(embed=embed, view=view)
                await ctx.send("Le règlement a été mis à jour.", delete_after=10)
                logger.info(f"Message des règles mis à jour avec ID: {message.id}")
                return
            except discord.NotFound:
                logger.warning("Message persistant introuvable, en recréation...")

        # Envoi du message s'il n'existe pas déjà
        try:
            message = await channel.send(embed=embed, view=view)
            logger.info(f"Message des règles envoyé avec ID: {message.id}")
        except discord.Forbidden:
            await ctx.send("Je n'ai pas les permissions nécessaires pour envoyer des messages dans ce salon.", delete_after=10)
            logger.error("Permission manquante pour envoyer un message dans le salon 'rules'.")
            return
        except Exception as e:
            await ctx.send("Une erreur est survenue lors de l'envoi du message.", delete_after=10)
            logger.error(f"Erreur lors de l'envoi du message des règles: {e}")
            return

        # Stocker le message dans la base
        success = await store_rules_message(guild_id, guild_name, channel.id, message.id)
        if success:
            await ctx.send(f"Règlement envoyé dans {channel.mention}.", delete_after=10)
            logger.info("Message des règles enregistré dans la base de données.")
        else:
            await ctx.send("Le règlement a été envoyé, mais une erreur est survenue lors de l'enregistrement.", delete_after=10)
            logger.error("Erreur lors de l'enregistrement du message des règles dans la base de données.")

    async def reload_persistent_views(self):
        """
        Recharge les vues persistantes pour les messages existants au démarrage.
        """
        await self.bot.wait_until_ready()
        logger.info("Rechargement des vues persistantes...")

        for guild in self.bot.guilds:
            guild_id = guild.id
            guild_name = guild.name

            # Récupérer le message persistant
            message_data = await get_persistent_message(guild_id, 'rules_embed', guild_name)
            if not message_data:
                continue

            channel = guild.get_channel(message_data["channel_id"])
            if not channel:
                logger.warning(f"Canal introuvable pour guild_id={guild_id}")
                continue

            try:
                message = await channel.fetch_message(message_data["message_id"])
                view = AcceptRulesView(self)
                self.bot.add_view(view, message_id=message.id)
                logger.info(f"Vue persistante ajoutée pour le message {message.id} dans le canal {channel.name}")
            except discord.NotFound:
                logger.warning(f"Message introuvable pour guild_id={guild_id}, suppression de la base.")
                await delete_persistent_message(guild_id, "rules_embed", guild_name)
            except Exception as e:
                logger.error(f"Erreur lors du rechargement des vues : {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("RulesCog prêt.")

    @setup_rules.error
    async def setup_rules_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Vous n'avez pas les permissions nécessaires pour utiliser cette commande.", delete_after=10)
            logger.warning(f"{ctx.author} a tenté d'utiliser setup_rules sans permissions.")
        else:
            await ctx.send("Une erreur est survenue lors de l'exécution de la commande.", delete_after=10)
            logger.error(f"Erreur dans setup_rules : {error}")

async def setup(bot: commands.Bot):
    await bot.add_cog(RulesCog(bot))
    logger.info("RulesCog chargé.")
