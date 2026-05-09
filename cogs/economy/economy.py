from __future__ import annotations

import logging
from datetime import date

import discord
from discord import app_commands
from discord.ext import commands

from cogs.economy.presenters import build_inventory_embed, build_shop_embed
from cogs.economy.services import DailyShopItem, EconomyService

logger = logging.getLogger(__name__)


class BuyItemButton(discord.ui.Button):
    def __init__(self, cog: "EconomyCog", item: DailyShopItem) -> None:
        super().__init__(label=f"Acheter {item.name}", style=discord.ButtonStyle.primary)
        self._cog = cog
        self._item = item

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Cette action doit etre faite dans un serveur.", ephemeral=True)
            return

        result = await self._cog.service.buy_item(
            guild_id=interaction.guild.id,
            guild_name=interaction.guild.name,
            discord_user_id=interaction.user.id,
            item=self._item,
        )
        if not result.purchased:
            await interaction.response.send_message(
                f"Pas assez de pieces pour acheter {self._item.name}. Balance actuelle: {result.balance}.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"{self._item.name} achete pour {self._item.price} pieces. Balance restante: {result.balance}.",
            ephemeral=True,
        )


class BuyItemView(discord.ui.View):
    def __init__(self, cog: "EconomyCog", items: tuple[DailyShopItem, ...]) -> None:
        super().__init__(timeout=300)
        for item in items:
            self.add_item(BuyItemButton(cog, item))


class TradeConfirmView(discord.ui.View):
    def __init__(
        self,
        cog: "EconomyCog",
        *,
        proposer: discord.Member,
        receiver: discord.Member,
        item_name: str,
    ) -> None:
        super().__init__(timeout=300)
        self._cog = cog
        self._proposer = proposer
        self._receiver = receiver
        self._item_name = item_name.strip()
        self._confirmed_user_ids: set[int] = set()

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id not in {self._proposer.id, self._receiver.id}:
            await interaction.response.send_message("Cet echange ne vous concerne pas.", ephemeral=True)
            return

        self._confirmed_user_ids.add(interaction.user.id)
        if self._confirmed_user_ids != {self._proposer.id, self._receiver.id}:
            await interaction.response.send_message("Confirmation enregistree.", ephemeral=True)
            return

        if not interaction.guild:
            await interaction.response.send_message("Serveur introuvable.", ephemeral=True)
            return

        result = await self._cog.service.transfer_item(
            guild_id=interaction.guild.id,
            guild_name=interaction.guild.name,
            from_discord_user_id=self._proposer.id,
            to_discord_user_id=self._receiver.id,
            item_name=self._item_name,
        )
        if not result.transferred:
            await interaction.response.send_message(
                f"Echange annule: {self._proposer.mention} ne possede plus `{self._item_name}`.",
                ephemeral=True,
            )
            self.stop()
            return

        button.disabled = True
        await interaction.response.edit_message(
            content=(
                f"Echange termine: `{self._item_name}` transfere de "
                f"{self._proposer.mention} vers {self._receiver.mention}."
            ),
            view=self,
        )
        self.stop()


class EconomyCog(commands.Cog):
    economy = app_commands.Group(name="economy", description="Commandes liees a l'economie")

    def __init__(self, bot: commands.Bot, economy_service: EconomyService) -> None:
        self.bot = bot
        self.service = economy_service
        self._shop_items: tuple[DailyShopItem, ...] = ()
        self._shop_date: date | None = None
        logger.info("EconomyCog initialized.")

    def _daily_shop(self) -> tuple[DailyShopItem, ...]:
        today = date.today()
        if self._shop_date != today or not self._shop_items:
            self._shop_items = self.service.generate_shop()
            self._shop_date = today
        return self._shop_items

    @economy.command(name="daily", description="Recuperer vos pieces quotidiennes.")
    async def daily(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Cette commande doit etre executee dans un serveur.", ephemeral=True)
            return

        role_names = [role.name for role in getattr(interaction.user, "roles", [])]
        result = await self.service.claim_daily(
            guild_id=interaction.guild.id,
            guild_name=interaction.guild.name,
            discord_user_id=interaction.user.id,
            role_names=role_names,
            claim_date=date.today(),
        )
        if not result.claimed:
            await interaction.followup.send(
                f"Vous avez deja recupere vos pieces aujourd'hui. Balance: {result.balance}.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Vous avez recu {result.amount} pieces. Balance: {result.balance}.",
            ephemeral=True,
        )

    @economy.command(name="shop", description="Afficher la boutique du jour.")
    async def shop(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        items = self._daily_shop()
        await interaction.followup.send(embed=build_shop_embed(items), view=BuyItemView(self, items), ephemeral=True)

    @economy.command(name="inventaire", description="Afficher votre inventaire.")
    async def inventaire(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Cette commande doit etre executee dans un serveur.", ephemeral=True)
            return

        profile, items = await self.service.list_inventory(
            guild_id=interaction.guild.id,
            guild_name=interaction.guild.name,
            discord_user_id=interaction.user.id,
        )
        await interaction.followup.send(
            embed=build_inventory_embed(
                display_name=interaction.user.display_name,
                profile=profile,
                items=items,
            ),
            ephemeral=True,
        )

    @economy.command(name="trade", description="Echanger un item avec un membre.")
    @app_commands.describe(user="Membre avec qui echanger", item_name="Nom exact de l'item a echanger")
    async def trade(self, interaction: discord.Interaction, user: discord.Member, item_name: str) -> None:
        await interaction.response.defer()
        if not interaction.guild:
            await interaction.followup.send("Cette commande doit etre executee dans un serveur.", ephemeral=True)
            return
        if user.id == interaction.user.id:
            await interaction.followup.send("Vous ne pouvez pas echanger avec vous-meme.", ephemeral=True)
            return
        if user.bot:
            await interaction.followup.send("Vous ne pouvez pas echanger avec un bot.", ephemeral=True)
            return
        if not item_name.strip():
            await interaction.followup.send("Nom d'item invalide.", ephemeral=True)
            return

        view = TradeConfirmView(
            self,
            proposer=interaction.user,
            receiver=user,
            item_name=item_name,
        )
        await interaction.followup.send(
            f"{interaction.user.mention} propose `{item_name.strip()}` a {user.mention}.",
            view=view,
        )


async def setup(bot: commands.Bot) -> None:
    economy_service = getattr(bot, "economy_service", None)
    if economy_service is None:
        logger.error("economy_service is not initialized. EconomyCog will not be loaded.")
        return

    await bot.add_cog(EconomyCog(bot, economy_service))
    logger.info("EconomyCog loaded.")
