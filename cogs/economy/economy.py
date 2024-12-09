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

# =============================
# Request Manager (Simplifié)
# =============================
# Ce gestionnaire de requêtes sert d'exemple. 
# Lorsqu'une commande est exécutée, on vérifie si l'utilisateur est admin:
# - Admin -> haute priorité, exécution immédiate.
# - Sinon -> basse priorité, on simule un délai.
# En pratique, on pourrait avoir une vraie file d'attente avec priorités.

class RequestManager:
    def __init__(self):
        pass

    async def handle_request(self, interaction: discord.Interaction, priority: str):
        # Si admin (priority=high), on exécute direct
        # Sinon, on simule un délai (ex: 1 seconde)
        if priority == "low":
            # On pourrait en faire plus complexe (files d'attente, horaire creux, etc.)
            await asyncio.sleep(1)
        # Après ce délai, la commande se poursuit

request_manager = RequestManager()

def with_request_priority():
    """Décorateur pour gérer la priorité des requêtes."""
    def decorator(func):
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            # Déterminer la priorité : si admin -> high, sinon low
            priority = "high" if interaction.user.guild_permissions.administrator else "low"
            await request_manager.handle_request(interaction, priority)
            return await func(self, interaction, *args, **kwargs)
        return wrapper
    return decorator

# =============================
# Vue et Boutons pour la Boutique
# =============================
class BuyItemView(discord.ui.View):
    def __init__(self, cog, items: List[Dict[str, Any]]):
        super().__init__(timeout=300)
        self.cog = cog
        self.items = items
        # Créez un bouton par item
        for i, item in enumerate(items):
            self.add_item(BuyButton(label=f"Acheter {item['name']}", style=discord.ButtonStyle.primary, item_index=i, cog=cog))

class BuyButton(discord.ui.Button):
    def __init__(self, label, style, item_index, cog):
        super().__init__(label=label, style=style)
        self.item_index = item_index
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        # Acheter l'item correspondant
        item = self.cog.daily_shop_items[self.item_index]
        economy_data = await self.cog.data.get_economy_data()
        user_id = str(interaction.user.id)
        user_info = economy_data.setdefault(user_id, {"balance":0,"last_claim":None,"items":[]})
        if user_info["balance"] < item["price"]:
            await interaction.response.send_message("Vous n'avez pas assez de pièces pour acheter cet item.", ephemeral=True)
            return
        # Débiter et ajouter l'item à l'inventaire
        user_info["balance"] -= item["price"]
        user_info["items"].append(item["name"])
        await self.cog.data.save_economy_data(economy_data)
        await interaction.response.send_message(f"Vous avez acheté {item['name']} pour {item['price']} pièces !", ephemeral=True)

# =============================
# Vue et Boutons pour le Trade
# =============================
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
    async def proposer_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.proposer.id:
            await interaction.response.send_message("Vous n'êtes pas le proposeur de cet échange.", ephemeral=True)
            return
        self.proposer_confirmed = True
        await interaction.response.send_message("Proposeur a confirmé.", ephemeral=True)
        await self.check_trade(interaction)

    @discord.ui.button(label="Confirmer (Receveur)", style=discord.ButtonStyle.green)
    async def receveur_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.receveur.id:
            await interaction.response.send_message("Vous n'êtes pas le receveur de cet échange.", ephemeral=True)
            return
        self.receveur_confirmed = True
        await interaction.response.send_message("Receveur a confirmé.", ephemeral=True)
        await self.check_trade(interaction)

    async def check_trade(self, interaction: discord.Interaction):
        if self.proposer_confirmed and self.receveur_confirmed:
            # Effectuer le transfert
            economy_data = await self.cog.data.get_economy_data()
            proposer_id = str(self.proposer.id)
            receveur_id = str(self.receveur.id)

            proposer_info = economy_data.setdefault(proposer_id, {"balance":0,"last_claim":None,"items":[]})
            receveur_info = economy_data.setdefault(receveur_id, {"balance":0,"last_claim":None,"items":[]})

            if self.item_name not in proposer_info["items"]:
                await interaction.followup.send("Le proposeur n'a plus l'item, échange annulé.", ephemeral=True)
                return

            # Transfert de l'item
            proposer_info["items"].remove(self.item_name)
            receveur_info["items"].append(self.item_name)
            await self.cog.data.save_economy_data(economy_data)
            await interaction.followup.send(f"Échange complété ! {self.item_name} transféré de {self.proposer.mention} à {self.receveur.mention}.", ephemeral=True)
            self.stop()

# =============================
# Cog Economy
# =============================
class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.daily_shop_items = []
        self.shop_refresh_time = time(hour=1, minute=0, second=0)  # 1h du matin UTC
        self.refresh_shop_task.start()

    def cog_unload(self):
        self.refresh_shop_task.cancel()

    # Réactualise la boutique chaque jour à 1h du matin
    @tasks.loop(time=shop_refresh_time)
    async def refresh_shop_task(self):
        await self.refresh_shop()

    async def refresh_shop(self):
        # Générer 4 items aléatoires
        possible_items = ["Skin Rouge", "Skin Bleu", "Skin Vert", "Skin Jaune", "Skin Épique", "Skin Légendaire"]
        self.daily_shop_items = []
        for _ in range(4):
            item = random.choice(possible_items)
            price = random.randint(100,500)
            self.daily_shop_items.append({"name": item, "price": price})
        logger.info("Boutique du jour rafraîchie.")

    @app_commands.command(name="economy", description="Commandes liées à l'économie")
    @app_commands.guild_only()
    async def economy_parent(self, interaction: discord.Interaction):
        await interaction.response.send_message("Utilisez les sous-commandes : /economy daily, /economy shop, /economy trade, /economy inventaire", ephemeral=True)

    @economy_parent.command(name="daily", description="Récupérer votre somme journalière")
    @enqueue_request()
    async def daily(self, interaction: discord.Interaction):
        economy_data = await self.data.get_economy_data()
        user_id = str(interaction.user.id)
        user_info = economy_data.setdefault(user_id, {"balance":0,"last_claim":None,"items":[]})

        now = datetime.utcnow()
        last_claim_str = user_info["last_claim"]
        if last_claim_str:
            last_claim = datetime.fromisoformat(last_claim_str)
            if last_claim.date() == now.date():
                await interaction.response.send_message("Vous avez déjà récupéré votre argent quotidien aujourd'hui. Revenez demain !", ephemeral=True)
                return

        # Déterminer la récompense de base
        base_amount = 100
        guild = interaction.guild
        if guild:
            member = guild.get_member(interaction.user.id)
            if member:
                # Si role bon joueur => 200 pièces au lieu de 100
                bon_joueur_role = discord.utils.get(guild.roles, name="bon joueur")
                booster_role = discord.utils.get(guild.roles, name="booster")

                if bon_joueur_role and bon_joueur_role in member.roles:
                    base_amount = 200

                # Si booster => x1.25
                if booster_role and booster_role in member.roles:
                    base_amount = int(base_amount * 1.25)

        user_info["balance"] += base_amount
        user_info["last_claim"] = now.isoformat()
        await self.data.save_economy_data(economy_data)
        await interaction.response.send_message(f"Vous avez reçu {base_amount} pièces aujourd'hui !", ephemeral=True)

    @economy_parent.command(name="shop", description="Affiche la boutique du jour")
    @enqueue_request()
    async def shop(self, interaction: discord.Interaction):
        if not self.daily_shop_items:
            # Si la boutique n'est pas encore chargée, la créer maintenant
            await self.refresh_shop()

        embed = discord.Embed(title="Boutique du Jour", color=discord.Color.blue())
        for item in self.daily_shop_items:
            embed.add_field(name=item["name"], value=f"Prix: {item['price']} pièces", inline=False)

        view = BuyItemView(self, self.daily_shop_items)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @economy_parent.command(name="trade", description="Échange d'items entre joueurs")
    @enqueue_request()
    @app_commands.describe(user="Joueur avec qui échanger", item_name="Nom de l'item à échanger")
    async def trade(self, interaction: discord.Interaction, user: discord.Member, item_name: str):
        if user == interaction.user:
            await interaction.response.send_message("Vous ne pouvez pas échanger avec vous-même.", ephemeral=True)
            return

        # Vérifier que le proposeur possède l'item
        economy_data = await self.data.get_economy_data()
        proposer_id = str(interaction.user.id)
        proposer_info = economy_data.setdefault(proposer_id, {"balance":0,"last_claim":None,"items":[]})
        if item_name not in proposer_info["items"]:
            await interaction.response.send_message("Vous n'avez pas cet item dans votre inventaire.", ephemeral=True)
            return

        # Créer une vue pour confirmation
        view = TradeView(self, interaction.user, user, item_name)
        await interaction.response.send_message(
            f"{interaction.user.mention} propose d'échanger `{item_name}` à {user.mention}. Confirmez les deux pour finaliser.",
            view=view,
            ephemeral=True
        )

    @economy_parent.command(name="inventaire", description="Affiche l'inventaire du joueur")
    @enqueue_request()
    async def inventaire(self, interaction: discord.Interaction):
        economy_data = await self.data.get_economy_data()
        user_id = str(interaction.user.id)
        user_info = economy_data.get(user_id, {"balance":0,"last_claim":None,"items":[]})

        balance = user_info.get("balance",0)
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
    logger.info("Economy Cog chargé avec succès.")
