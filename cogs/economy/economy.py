# cogs/economy/economy.py
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta, time
import asyncio
import random

from cogs.utilities.data_manager import DataManager
from cogs.utilities.request_manager import enqueue_request

logger = logging.getLogger("discord.economy")

class RequestManager:
    def __init__(self):
        pass

    async def handle_request(self, interaction: Any, priority: str):
        if priority == "low":
            await asyncio.sleep(1)

request_manager = RequestManager()

def with_request_priority():
    def decorator(func):
        async def wrapper(self, interaction: Any, *args, **kwargs):
            priority = "high" if interaction.user.guild_permissions.administrator else "low"
            await request_manager.handle_request(interaction, priority)
            return await func(self, interaction, *args, **kwargs)
        return wrapper
    return decorator

class BuyItemView(discord.ui.View):
    def __init__(self, cog, items: List[Dict[str, Any]]):
        super().__init__(timeout=300)
        self.cog = cog
        self.items = items
        for i, item in enumerate(items):
            self.add_item(BuyButton(label=f"Acheter {item['name']}", style=discord.ButtonStyle.primary, item_index=i, cog=cog))

class BuyButton(discord.ui.Button):
    def __init__(self, label, style, item_index, cog):
        super().__init__(label=label, style=style)
        self.item_index = item_index
        self.cog = cog

    async def callback(self, interaction: Any):
        item = self.cog.daily_shop_items[self.item_index]
        economy_data = await self.cog.data.get_economy_data()
        user_id = str(interaction.user.id)
        user_info = economy_data.setdefault(user_id, {"balance":0, "last_claim":None, "items":[]})
        if user_info["balance"] < item["price"]:
            await interaction.response.send_message("Vous n'avez pas assez de pièces pour acheter cet item.", ephemeral=True)
            return
        user_info["balance"] -= item["price"]
        user_info["items"].append(item["name"])
        await self.cog.data.save_economy_data(economy_data)
        await interaction.response.send_message(f"Vous avez acheté {item['name']} pour {item['price']} pièces !", ephemeral=True)

class TradeView(discord.ui.View):
    def __init__(self, cog, proposer: discord.Member, receveur: discord.Member, item_name: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.proposer = proposer
        self.receveur = receveur
        self.item_name = item_name
        self.proposer_confirmed = False
        self.receveur_confirmed = False

    @discord.ui.button(label="Confirmer (Proposeur)", style=discord.ButtonStyle.green)
    async def proposer_confirm(self, interaction: Any, button: discord.ui.Button):
        if interaction.user.id != self.proposer.id:
            await interaction.response.send_message("Vous n'êtes pas le proposeur de cet échange.", ephemeral=True)
            return
        self.proposer_confirmed = True
        await interaction.response.send_message("Proposeur a confirmé.", ephemeral=True)
        await self.check_trade(interaction)

    @discord.ui.button(label="Confirmer (Receveur)", style=discord.ButtonStyle.green)
    async def receveur_confirm(self, interaction: Any, button: discord.ui.Button):
        if interaction.user.id != self.receveur.id:
            await interaction.response.send_message("Vous n'êtes pas le receveur de cet échange.", ephemeral=True)
            return
        self.receveur_confirmed = True
        await interaction.response.send_message("Receveur a confirmé.", ephemeral=True)
        await self.check_trade(interaction)

    async def check_trade(self, interaction: Any):
        if self.proposer_confirmed and self.receveur_confirmed:
            economy_data = await self.cog.data.get_economy_data()
            proposer_id = str(self.proposer.id)
            receveur_id = str(self.receveur.id)

            proposer_info = economy_data.setdefault(proposer_id, {"balance":0, "last_claim":None, "items":[]})
            receveur_info = economy_data.setdefault(receveur_id, {"balance":0, "last_claim":None, "items":[]})

            if self.item_name not in proposer_info["items"]:
                await interaction.followup.send("Le proposeur n'a plus l'item, échange annulé.", ephemeral=True)
                return

            proposer_info["items"].remove(self.item_name)
            receveur_info["items"].append(self.item_name)
            await self.cog.data.save_economy_data(economy_data)
            await interaction.followup.send(f"Échange complété ! {self.item_name} transféré de {self.proposer.mention} à {self.receveur.mention}.", ephemeral=True)
            self.stop()

class Economy(commands.Cog):
    shop_refresh_time = time(hour=1, minute=0, second=0)

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.daily_shop_items = []
        self.refresh_shop_task.start()

    def cog_unload(self):
        self.refresh_shop_task.cancel()

    @tasks.loop(time=shop_refresh_time)
    async def refresh_shop_task(self):
        await self.refresh_shop()

    async def refresh_shop(self):
        possible_items = ["Skin Rouge", "Skin Bleu", "Skin Vert", "Skin Jaune", "Skin Épique", "Skin Légendaire"]
        self.daily_shop_items = []
        for _ in range(4):
            item = random.choice(possible_items)
            price = random.randint(100, 500)
            self.daily_shop_items.append({"name": item, "price": price})
        logger.info("Boutique du jour rafraîchie.")

# MODIF: On crée un groupe de commandes au lieu d'une simple commande
economy_parent = app_commands.Group(name="economy", description="Commandes liées à l'économie")

@economy_parent.command(name="daily", description="Récupérer votre somme journalière")
@enqueue_request()
async def daily(interaction: Any):
    cog: Economy = interaction.client.get_cog("Economy")
    economy_data = await cog.data.get_economy_data()
    user_id = str(interaction.user.id)
    user_info = economy_data.setdefault(user_id, {"balance":0, "last_claim":None, "items":[]})

    now = datetime.utcnow()
    last_claim_str = user_info["last_claim"]
    if last_claim_str:
        last_claim = datetime.fromisoformat(last_claim_str)
        if last_claim.date() == now.date():
            await interaction.response.send_message("Vous avez déjà récupéré votre argent quotidien aujourd'hui. Revenez demain !", ephemeral=True)
            return

    base_amount = 100
    guild = interaction.guild
    if guild:
        member = guild.get_member(interaction.user.id)
        if member:
            bon_joueur_role = discord.utils.get(guild.roles, name="bon joueur")
            booster_role = discord.utils.get(guild.roles, name="booster")

            if bon_joueur_role and bon_joueur_role in member.roles:
                base_amount = 200

            if booster_role and booster_role in member.roles:
                base_amount = int(base_amount * 1.25)

    user_info["balance"] += base_amount
    user_info["last_claim"] = now.isoformat()
    await cog.data.save_economy_data(economy_data)
    await interaction.response.send_message(f"Vous avez reçu {base_amount} pièces aujourd'hui !", ephemeral=True)

@economy_parent.command(name="shop", description="Affiche la boutique du jour")
@enqueue_request()
async def shop(interaction: Any):
    cog: Economy = interaction.client.get_cog("Economy")
    if not cog.daily_shop_items:
        await cog.refresh_shop()

    embed = discord.Embed(title="Boutique du Jour", color=discord.Color.blue())
    for item in cog.daily_shop_items:
        embed.add_field(name=item["name"], value=f"Prix: {item['price']} pièces", inline=False)

    view = BuyItemView(cog, cog.daily_shop_items)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@economy_parent.command(name="trade", description="Échange d'items entre joueurs")
@enqueue_request()
@app_commands.describe(user="Joueur avec qui échanger", item_name="Nom de l'item à échanger")
async def trade(interaction: Any, user: discord.Member, item_name: str):
    if user == interaction.user:
        await interaction.response.send_message("Vous ne pouvez pas échanger avec vous-même.", ephemeral=True)
        return

    cog: Economy = interaction.client.get_cog("Economy")
    economy_data = await cog.data.get_economy_data()
    proposer_id = str(interaction.user.id)
    proposer_info = economy_data.setdefault(proposer_id, {"balance":0, "last_claim":None, "items":[]})
    if item_name not in proposer_info["items"]:
        await interaction.response.send_message("Vous n'avez pas cet item dans votre inventaire.", ephemeral=True)
        return

    view = TradeView(cog, interaction.user, user, item_name)
    await interaction.response.send_message(
        f"{interaction.user.mention} propose d'échanger `{item_name}` à {user.mention}. Confirmez les deux pour finaliser.",
        view=view,
        ephemeral=True
    )

@economy_parent.command(name="inventaire", description="Affiche l'inventaire du joueur")
@enqueue_request()
async def inventaire(interaction: Any):
    cog: Economy = interaction.client.get_cog("Economy")
    economy_data = await cog.data.get_economy_data()
    user_id = str(interaction.user.id)
    user_info = economy_data.get(user_id, {"balance":0, "last_claim":None, "items":[]})

    balance = user_info.get("balance", 0)
    items = user_info.get("items", [])
    embed = discord.Embed(title=f"Inventaire de {interaction.user.display_name}", color=discord.Color.gold())
    embed.add_field(name="Balance", value=f"{balance} pièces", inline=False)
    if items:
        embed.add_field(name="Items", value="\n".join(items), inline=False)
    else:
        embed.add_field(name="Items", value="Aucun item", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
    bot.tree.add_command(economy_parent)  # MODIF: Ajout du groupe de commandes au tree
    logger.info("Economy Cog chargé avec succès.")
