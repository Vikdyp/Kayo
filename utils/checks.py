import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

from cogs.rules.service.rules_services import has_accepted_rules, get_rules_channel_id
from cogs.ranking.services.assign_rank_service import get_channel_id, valorant_account_linked, valorant_puuid_present

async def _send_rules_prompt(target, guild: discord.Guild, channel_id: Optional[int]):
    if isinstance(target, discord.Interaction):
        if channel_id:
            link = f"https://discord.com/channels/{guild.id}/{channel_id}"
            if not target.response.is_done():
                await target.response.send_message(
                    f"Veuillez accepter le règlement ici : {link}",
                    ephemeral=True,
                )
            else:
                await target.followup.send(
                    f"Veuillez accepter le règlement ici : {link}",
                    ephemeral=True,
                )
        else:
            if not target.response.is_done():
                await target.response.send_message(
                    "Veuillez accepter le règlement avant d'utiliser cette commande.",
                    ephemeral=True,
                )
            else:
                await target.followup.send(
                    "Veuillez accepter le règlement avant d'utiliser cette commande.",
                    ephemeral=True,
                )
    else:  # commands.Context
        if channel_id:
            await target.send(
                f"Veuillez accepter le règlement dans <#{channel_id}>.",
                delete_after=10,
            )
        else:
            await target.send(
                "Veuillez accepter le règlement avant d'utiliser cette commande.",
                delete_after=10,
            )


def rules_check():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return True
        if ctx.command and ctx.command.qualified_name == "setup_rules":
            return True
        if await has_accepted_rules(ctx.author.id):
            return True
        channel_id = await get_rules_channel_id(ctx.guild.id, ctx.guild.name)
        await _send_rules_prompt(ctx, ctx.guild, channel_id)
        return False
    return commands.check(predicate)


async def rules_interaction_check(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        return True
    if interaction.command and interaction.command.qualified_name == "setup_rules":
        return True
    if await has_accepted_rules(interaction.user.id):
        return True
    channel_id = await get_rules_channel_id(interaction.guild.id, interaction.guild.name)
    await _send_rules_prompt(interaction, interaction.guild, channel_id)
    return False


def valorant_link_required():
    async def predicate(interaction: discord.Interaction) -> bool:
        # 1) L'utilisateur a-t-il déjà lié son compte (ligne dans valorant_info) ?
        linked = await valorant_account_linked(interaction.user.id)
        if not linked:
            # On tente de récupérer le salon configuré pour l'action "rang"
            channel_id = None
            if interaction.guild_id is not None:
                channel_id = await get_channel_id(interaction.guild_id, "rang")

            if channel_id:
                salon = f"<#{channel_id}>"
            else:
                salon = "`#rang`"  # fallback texte si pas configuré

            msg = (
                f"❌ Vous n'avez pas encore lié votre compte Valorant.\n"
                f"Veuillez vous rendre dans le salon {salon}"
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return False

        # 2) Si oui, est-ce que le PUUID est déjà récupéré ?
        puuid_ok = await valorant_puuid_present(interaction.user.id)
        if not puuid_ok:
            # On peut aussi préciser le salon ici si besoin, mais souvent
            # on informe simplement que c'est en cours de récupération.
            msg = (
                "⏳ Votre compte Valorant est bien lié, "
                "mais il n'est pas encore disponible (en cours de récupération).\n"
                "Réessayez dans quelques instants ou vérifiez que la liaison s'est bien terminée."
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return False

        # 3) Si on arrive ici, l'utilisateur est bien dans valorant_info ET puuid n'est pas NULL
        return True

    return app_commands.check(predicate)