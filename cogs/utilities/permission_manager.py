#cogs\utilities\permission_manager.py
import discord
from discord import app_commands

def is_admin():
    """Check si l'utilisateur a les permissions administrateur."""
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

def has_role(role_name: str):
    """Check si l'utilisateur possède un rôle spécifique."""
    async def predicate(interaction: discord.Interaction) -> bool:
        return any(r.name == role_name for r in interaction.user.roles)
    return app_commands.check(predicate)
