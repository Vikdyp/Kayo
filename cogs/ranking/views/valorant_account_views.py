# cogs/ranking/views/valorant_account_views.py
"""Persistent views and modals for Valorant account linking."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from cogs.ranking.assign_rank import EmbedCog

logger = logging.getLogger(__name__)


class PseudoTagModal(discord.ui.Modal):
    """Modal pour renseigner ou changer son pseudo/tag Valorant."""

    def __init__(self, user: discord.User, cog: "EmbedCog", is_change: bool = False):
        title = "Changer de compte Valorant" if is_change else "Renseignez votre Pseudo et Tag Valorant"
        super().__init__(title=title)
        self.user = user
        self.cog = cog
        self.is_change = is_change

        self.pseudo = discord.ui.TextInput(
            label="Pseudo",
            placeholder="Entrez votre pseudo Valorant (exemple: Swyzin)",
            max_length=32,
            required=True,
        )
        self.tag = discord.ui.TextInput(
            label="Tag",
            placeholder="Entrez votre tag Valorant sans le # (exemple: meow)",
            max_length=6,
            required=True,
        )
        self.add_item(self.pseudo)
        self.add_item(self.tag)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        svc = self.cog._ranking_svc
        pseudo = self.pseudo.value.strip()
        tag = self.tag.value.strip()

        if not pseudo:
            await interaction.response.send_message(
                "Le pseudo ne doit pas etre vide.",
                ephemeral=True,
            )
            return

        if not tag.isalnum():
            await interaction.response.send_message(
                "Le tag ne doit contenir que des lettres et des chiffres.",
                ephemeral=True,
            )
            return

        existing_discord_id = await svc.get_user_by_pseudo_tag(pseudo, tag)
        if existing_discord_id:
            if existing_discord_id == self.user.id:
                await interaction.response.send_message(
                    "Vous avez deja enregistre ce pseudo et tag Valorant.",
                    ephemeral=True,
                )
                return

            existing_user = self.cog.bot.get_user(existing_discord_id)
            if not existing_user:
                try:
                    existing_user = await self.cog.bot.fetch_user(existing_discord_id)
                except discord.NotFound:
                    existing_user = None

            await interaction.response.send_message(
                "Ce pseudo et tag Valorant sont deja utilises par un autre utilisateur.",
                ephemeral=True,
            )
            if existing_user:
                await self.cog.notify_duplicate_pseudo_tag(
                    existing_user,
                    self.user,
                    pseudo,
                    tag,
                    interaction.guild,
                )
            return

        try:
            if self.is_change:
                success = await svc.reset_for_account_change(
                    interaction.user.id,
                    pseudo,
                    tag,
                )
                message = (
                    f"Votre compte Valorant a ete change vers : {pseudo}#{tag}\n"
                    "La mise a jour de votre rang commencera bientot."
                )
            else:
                success = await svc.link_account(interaction.user.id, pseudo, tag)
                message = f"Vos informations Valorant ont ete enregistrees : {pseudo}#{tag}"

            if success:
                await interaction.response.send_message(message, ephemeral=True)
                action = "changed" if self.is_change else "registered"
                logger.info("User %s %s Valorant: %s#%s", interaction.user, action, pseudo, tag)
            else:
                await interaction.response.send_message(
                    "Une erreur est survenue. Veuillez reessayer plus tard.",
                    ephemeral=True,
                )
        except Exception as exc:
            logger.error("Erreur lors de l'enregistrement pour %s: %s", interaction.user, exc)
            await interaction.response.send_message(
                "Une erreur est survenue. Veuillez reessayer plus tard.",
                ephemeral=True,
            )


class EmbedButtonsView(discord.ui.View):
    """Vue avec les boutons pour l'embed de gestion Valorant."""

    def __init__(self, cog: "EmbedCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Renseigner Pseudo/Tag Valorant",
        style=discord.ButtonStyle.primary,
        custom_id="button:pseudo_tag",
    )
    async def pseudo_tag_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        modal = PseudoTagModal(interaction.user, self.cog, is_change=False)
        if not interaction.response.is_done():
            await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Changer de compte Valorant",
        style=discord.ButtonStyle.secondary,
        custom_id="button:change_valo_account",
    )
    async def change_account_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.cog._ranking_svc.account_linked(interaction.user.id):
            await interaction.response.send_message(
                "Vous n'avez pas encore de compte Valorant lie. "
                "Utilisez le bouton bleu pour en lier un.",
                ephemeral=True,
            )
            return

        modal = PseudoTagModal(interaction.user, self.cog, is_change=True)
        if not interaction.response.is_done():
            await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Effacer mes donnees Valorant",
        style=discord.ButtonStyle.danger,
        custom_id="button:delete_valo_data",
    )
    async def delete_valo_data_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        try:
            success = await self.cog._ranking_svc.delete_account(interaction.user.id)
            if success:
                await interaction.followup.send(
                    "Vos donnees Valorant ont ete supprimees de la base de donnees.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "Une erreur est survenue lors de la suppression de vos donnees.",
                    ephemeral=True,
                )
        except Exception as exc:
            logger.error("Erreur suppression donnees Valorant pour %s: %s", interaction.user, exc)
            await interaction.followup.send(
                "Une erreur est survenue lors de la suppression de vos donnees.",
                ephemeral=True,
            )
