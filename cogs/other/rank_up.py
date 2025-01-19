import discord
from discord.ext import commands

# Dictionnaire de correspondance rôle -> niveau
# Plus le numéro est petit, plus le rôle est élevé.
ROLE_RANK = {
    "radiant": 1,
    "immortel": 2,
    "ascendant": 3,
    "diamant": 4,
    "platine": 5,
    "or": 6,
    "argent": 7,
    "bronze": 8,
    "fer": 9
}

class RoleChangeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Remplace cette variable par l'ID du salon où le bot doit envoyer les messages de log
        self.log_channel_id = 1236733103687340144

    def top_role_by_rank(self, role_names):
        """
        Renvoie une tuple (nom_role, rang) pour le rôle le plus élevé parmi une liste de noms de rôles (en minuscule).
        Si aucun rôle n'est reconnu dans ROLE_RANK, renvoie None.
        """
        eligible = [(role, ROLE_RANK.get(role)) for role in role_names if ROLE_RANK.get(role)]
        if eligible:
            # Le rôle avec le rang le plus bas est considéré comme le plus haut (promotion)
            return sorted(eligible, key=lambda x: x[1])[0]
        return None

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Exclure le rôle @everyone
        before_role_names = [role.name.lower() for role in before.roles if role.name != "@everyone"]
        after_role_names  = [role.name.lower() for role in after.roles if role.name != "@everyone"]

        # Si aucun changement n'est détecté, on ne fait rien.
        if set(before_role_names) == set(after_role_names):
            return

        before_top = self.top_role_by_rank(before_role_names)
        after_top = self.top_role_by_rank(after_role_names)

        # Si aucun des rôles ne correspond au dictionnaire, on ne fait rien.
        if not before_top or not after_top:
            return

        before_role, before_rank = before_top
        after_role, after_rank = after_top

        log_channel = self.bot.get_channel(self.log_channel_id)
        if not log_channel:
            print(f"Salon avec l'ID {self.log_channel_id} non trouvé.")
            return

        # Cas promotion : le nouveau rang est inférieur numériquement (meilleur rang)
        if before_rank > after_rank:
            # Idée de message 1 : "@user vient de passer {nouveau rang} bien jouer!"
            message = f"{after.mention} vient de passer **{after_role.capitalize()}**. Bien joué !"
            # Tu peux tester d'autres variantes :
            # message = f"Félicitations {after.mention}, promotion vers **{after_role.capitalize()}** !"
            await log_channel.send(message)

        # Cas rétrogradation : le nouveau rang est supérieur numériquement (rang moins avantageux)
        elif before_rank < after_rank:
            # Idée de message 1 : "@user vient de derank {nouveau rang} force a toi"
            message = f"{after.mention} vient de derank en **{after_role.capitalize()}**. Force à toi !"
            # Autre variante possible :
            # message = f"Dommage {after.mention}, tu es rétrogradé à **{after_role.capitalize()}**."
            await log_channel.send(message)
        # Si le rôle principal n'a pas changé, pas de message à envoyer.
        else:
            return

async def setup(bot):
    await bot.add_cog(RoleChangeCog(bot))
