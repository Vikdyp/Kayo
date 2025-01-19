import discord
from discord.ext import commands
from discord.ui import Button, View
import random
import logging
from utils.database import database  # Assurez-vous que le chemin est correct

logger = logging.getLogger("event_cog")

# Constantes / Configuration
MIN_INVITES_REQUIRED = 3    # Nombre minimum d'invitations nécessaires pour participer
OBJECTIF_PARTICIPANTS = 65  # Objectif du nombre de participants à atteindre
MESSAGE_TYPE_EVENT = "event"  # Type pour l'event dans persistent_messages

# ----------------- Bouton et Vue -----------------

class ParticipateButton(Button):
    def __init__(self, cog, event_embed):
        super().__init__(style=discord.ButtonStyle.success, label="Participer")
        self.cog = cog
        self.event_embed = event_embed

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user

        # Vérification du nombre d'invitations
        invite_count = await self.cog.get_invite_count(user.id)
        if invite_count < MIN_INVITES_REQUIRED:
            await interaction.response.send_message(
                f"Tu dois avoir invité au moins {MIN_INVITES_REQUIRED} membres pour participer. Tu en as invité {invite_count}.",
                ephemeral=True
            )
            return

        # Vérification de l'inscription
        if await self.cog.is_participant(user.id):
            await interaction.response.send_message("Tu es déjà inscrit(e) à l'événement.", ephemeral=True)
            return

        # Ajout en base de données
        await self.cog.add_participant(user.id)
        current_count = await self.cog.get_participant_count()
        updated_embed = self.event_embed.copy()
        updated_embed.set_field_at(
            0, name="👤Participants", value=f"{current_count} / {OBJECTIF_PARTICIPANTS}", inline=False
        )

        await interaction.response.edit_message(embed=updated_embed)
        await interaction.followup.send("Tu es désormais inscrit(e) à l'événement !", ephemeral=True)


class EventView(View):
    def __init__(self, cog, event_embed, timeout: float = None):
        super().__init__(timeout=timeout)
        self.add_item(ParticipateButton(cog, event_embed))


# ----------------- Cog Principal -----------------

class EventCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_internal_server_id(self, guild: discord.Guild) -> int:
        """
        Récupère l'ID interne du serveur en consultant la table serveur_id.
        La colonne 'guild_id' dans serveur_id correspond à l'ID réel de Discord.
        """
        await database.ensure_connected()
        query = "SELECT id FROM serveur_id WHERE guild_id = $1;"
        internal_id = await database.fetchval(query, guild.id)
        if not internal_id:
            logger.error(f"Serveur non trouvé dans la table serveur_id pour guild_id {guild.id}.")
        return internal_id

    async def persist_message(self, guild: discord.Guild, channel_id: int, message_id: int):
        """
        Enregistre dans persistent_messages l'ID du salon, l'ID du message,
        le type de message et l'ID interne du serveur.
        La colonne requester_id reste à NULL.
        """
        internal_server_id = await self.get_internal_server_id(guild)
        if not internal_server_id:
            return

        await database.ensure_connected()
        query = """
        INSERT INTO persistent_messages (channel_id, message_id, message_type, guild_id)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (guild_id, message_type) DO UPDATE
            SET channel_id = EXCLUDED.channel_id,
                message_id = EXCLUDED.message_id;
        """
        await database.execute(query, channel_id, message_id, MESSAGE_TYPE_EVENT, internal_server_id)
        logger.info(f"Message persistant enregistré pour le server interne {internal_server_id}.")

    async def reattach_event_message(self, guild: discord.Guild):
        """
        Sur le démarrage du bot, rechercher dans persistent_messages un message de type event pour ce serveur.
        Si trouvé, récupère le message et réattache la vue du bouton.
        Si le message n'est pas trouvé, recréer l'embed d'événement.
        """
        internal_server_id = await self.get_internal_server_id(guild)
        if not internal_server_id:
            return

        await database.ensure_connected()
        query = """
        SELECT channel_id, message_id FROM persistent_messages
        WHERE guild_id = $1 AND message_type = $2;
        """
        row = await database.fetchrow(query, internal_server_id, MESSAGE_TYPE_EVENT)
        channel = None
        message = None

        if row:
            channel = self.bot.get_channel(row["channel_id"])
            if channel is None:
                logger.error(f"Salon {row['channel_id']} non trouvé pour le message persistant.")
            else:
                try:
                    message = await channel.fetch_message(row["message_id"])
                except discord.NotFound:
                    logger.error("Message persistant non trouvé (404). Il a probablement été supprimé.")
                except Exception as e:
                    logger.error(f"Erreur lors de la récupération du message persistant: {e}")

        # Si le message n'existe pas, on recrée l'embed et on l'envoie, puis on met à jour la BDD
        if message is None:
            logger.info("Recréation du message d'événement persistant.")
            total_members = guild.member_count
            current_participants = await self.get_participant_count()
            embed = discord.Embed(
                title="🎁GIVEAWAY🎁",
                description=(
                    f"Participe à notre événement et tente de gagner 1 mois de Nitro ou une carte cadeau Valorant !\n\n"
                    f"Le concours se terminera quand nous aurons atteint l'objectif de participants.\n\n"
                    f"*Attention : seuls les membres ayant invité au moins {MIN_INVITES_REQUIRED} personnes peuvent participer.*"
                ),
                color=discord.Color.blue()
            )
            embed.add_field(name="👤Participants", value=f"{current_participants} / {OBJECTIF_PARTICIPANTS}", inline=False)
            embed.set_footer(text="Clique sur 'Participer' pour t'inscrire!")
            view = EventView(self, embed, timeout=None)

            try:
                # Envoi du message dans le même salon que précédemment ou dans le premier salon textuel si non défini
                if channel is None:
                    channel = guild.text_channels[0]
                message = await channel.send(embed=embed, view=view)
                # Met à jour la BDD avec le nouveau message
                await self.persist_message(guild, channel.id, message.id)
                logger.info(f"Message d'événement recréé et persistant enregistré dans le salon {channel.id}.")
            except Exception as e:
                logger.error(f"Erreur lors de la recréation du message d'événement persistant: {e}")
        else:
            # Le message est trouvé, réattache la vue
            total_members = guild.member_count
            current_participants = await self.get_participant_count()
            embed = discord.Embed(
                title="🎁GIVEAWAY🎁",
                description=(
                    f"Participe à notre événement et tente de gagner 1 mois de Nitro ou une carte cadeau Valorant !\n\n"
                    f"Le concours se terminera quand nous aurons atteint l'objectif de participants.\n\n"
                    f"*Attention : seuls les membres ayant invité au moins {MIN_INVITES_REQUIRED} personnes peuvent participer.*"
                ),
                color=discord.Color.blue()
            )
            embed.add_field(name="👤Participants", value=f"{current_participants} / {OBJECTIF_PARTICIPANTS}", inline=False)
            embed.set_footer(text="Clique sur 'Participer' pour t'inscrire!")
            view = EventView(self, embed, timeout=None)
            try:
                await message.edit(embed=embed, view=view)
                logger.info(f"Vue réattachée au message persistant dans le salon {channel.id}.")
            except Exception as e:
                logger.error(f"Erreur lors de la réattache de la vue: {e}")


    # Méthodes d'accès à la BDD pour l'invitation et participants

    async def get_invite_count(self, user_id: int) -> int:
        await database.ensure_connected()
        query = "SELECT count FROM invite_tracker WHERE inviter_id = $1;"
        result = await database.fetchval(query, user_id)
        return result if result is not None else 0

    async def add_participant(self, user_id: int):
        await database.ensure_connected()
        query = """
        INSERT INTO participant (user_id)
        VALUES ($1)
        ON CONFLICT (user_id) DO NOTHING;
        """
        await database.execute(query, user_id)
        logger.info(f"Participant ajouté : {user_id}")

    async def is_participant(self, user_id: int) -> bool:
        await database.ensure_connected()
        query = "SELECT user_id FROM participant WHERE user_id = $1;"
        result = await database.fetchval(query, user_id)
        return result is not None

    async def get_participant_count(self) -> int:
        await database.ensure_connected()
        query = "SELECT COUNT(*) FROM participant;"
        result = await database.fetchval(query)
        return result if result is not None else 0

    async def get_all_participants(self):
        await database.ensure_connected()
        query = "SELECT user_id FROM participant;"
        rows = await database.fetch(query)
        return [row['user_id'] for row in rows]

    # ----------------- Commandes -----------------

    @commands.command(name="send_event")
    async def send_event(self, ctx: commands.Context):
        """
        Envoie un embed d'événement avec un bouton pour participer.
        Seuls les membres ayant invité au moins MIN_INVITES_REQUIRED personnes pourront participer.
        L'embed affiche aussi le nombre actuel de membres du serveur et l'objectif de participants.
        """
        total_members = ctx.guild.member_count
        embed = discord.Embed(
            title="🎁GIVEAWAY🎁",
            description=f"Participe à notre événement et tente de gagner 1 mois de Nitro ou une carte cadeau Valorant !\n\nLe concours se terminera quand nous aurons atteint l'objectif de participants.\n\n*Attention : seuls les membres ayant invité au moins {MIN_INVITES_REQUIRED} personnes peuvent participer.*",
            color=discord.Color.blue()
        )
        embed.add_field(name="👤Participants", value=f"0 / {OBJECTIF_PARTICIPANTS}", inline=False)
        embed.set_footer(text="Clique sur 'Participer' pour t'inscrire!")
        view = EventView(self, embed, timeout=None)
        message = await ctx.send(embed=embed, view=view)

        # Persistance du message : on récupère l'ID interne du serveur puis on enregistre le message dans persistent_messages
        await self.persist_message(ctx.guild, message.channel.id, message.id)

    @commands.command(name="tirage")
    @commands.has_permissions(administrator=True)
    async def tirage(self, ctx: commands.Context):
        """
        Commande admin qui tire au sort un membre parmi ceux inscrits à l'événement.
        """
        participants = await self.get_all_participants()
        if not participants:
            await ctx.send("Aucun participant n'est inscrit pour le moment.")
            return

        gagnant_id = random.choice(participants)
        gagnant = ctx.guild.get_member(gagnant_id)
        if gagnant is None:
            await ctx.send("Le membre tiré au sort n'est plus dans le serveur.")
        else:
            await ctx.send(f"Félicitations {gagnant.mention}, tu es le(la) gagnant(e) du tirage au sort !")

    @tirage.error
    async def tirage_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Tu n'as pas la permission d'utiliser cette commande.")

    # ----------------- Réattachement au démarrage -----------------

    @commands.Cog.listener()
    async def on_ready(self):
        # À chaque démarrage, pour chaque serveur dans lequel le bot est, tenter de réattacher le message d'événement.
        for guild in self.bot.guilds:
            await self.reattach_event_message(guild)

async def setup(bot):
    await bot.add_cog(EventCog(bot))
