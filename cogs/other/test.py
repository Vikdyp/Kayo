import discord
from discord import app_commands
from discord.ext import commands
import io
import csv

# Liste des permissions à vérifier (vous pouvez l'ajuster)
PERMISSIONS_TO_CHECK = [
    "create_instant_invite",
    "kick_members",
    "ban_members",
    "administrator",
    "manage_channels",
    "manage_guild",
    "add_reactions",
    "view_audit_log",
    "priority_speaker",
    "stream",
    "view_channel",
    "send_messages",
    "send_tts_messages",
    "manage_messages",
    "embed_links",
    "attach_files",
    "read_message_history",
    "mention_everyone",
    "use_external_emojis",
    "connect",
    "speak",
    "mute_members",
    "deafen_members",
    "move_members",
    "use_vad",
    "manage_roles",
    "manage_webhooks",
    "manage_emojis"
]

class TestRolesCSVReportCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="test",
        description="Génère un rapport CSV comparatif des permissions des rôles par salon."
    )
    async def test(self, interaction: discord.Interaction):
        # Différer la réponse pour avoir le temps de générer le rapport.
        await interaction.response.defer(ephemeral=True)
        guild: discord.Guild = interaction.guild

        # On trie les rôles par position décroissante (du plus haut au plus bas)
        roles = sorted(guild.roles, key=lambda r: r.position, reverse=True)
        
        # On crée un buffer en mémoire pour le CSV
        output_buffer = io.StringIO()
        csv_writer = csv.writer(output_buffer)

        # Pour chaque salon, générer un tableau
        # On va structurer le CSV en sections, une section par salon.
        for channel in guild.channels:
            # On écrit une ligne indiquant le salon
            csv_writer.writerow([f"Salon : {channel.name} [{channel.type}]"])
            # Ligne vide pour séparer le titre
            csv_writer.writerow([])
            
            # Préparer l'en-tête : "Permission" suivi du nom de chaque rôle.
            header = ["Permission"] + [role.name for role in roles]
            csv_writer.writerow(header)
            
            # Pour chaque permission, écrire une ligne qui indique "✅" si le rôle dispose de la permission, sinon laisser vide.
            for perm in PERMISSIONS_TO_CHECK:
                # On formate le nom de la permission pour être plus lisible.
                perm_name = perm.replace("_", " ").title()
                row = [perm_name]
                for role in roles:
                    # Récupération de la permission pour le rôle dans ce salon.
                    perm_val = getattr(channel.permissions_for(role), perm, False)
                    row.append("✅" if perm_val else "")
                csv_writer.writerow(row)
            
            # Ajouter quelques lignes vides pour séparer les sections (salons)
            csv_writer.writerow([])
            csv_writer.writerow([])

        # Positionner le curseur au début du buffer
        output_buffer.seek(0)
        file = discord.File(fp=io.BytesIO(output_buffer.getvalue().encode("utf-8")), filename="rapport_permissions.csv")
        await interaction.followup.send(content="Voici le rapport CSV comparatif des permissions. Ouvrez-le dans un tableur pour une lecture facilitée.", file=file, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(TestRolesCSVReportCog(bot))
