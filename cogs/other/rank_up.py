import discord
from discord.ext import commands
import asyncio
import time

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
        # Remplace par l'ID du salon de logs
        self.log_channel_id = 1236733103687340144

        # Mémorise temporairement les rôles retirés en attendant
        # de voir si un nouveau rôle arrive pour ce membre
        #
        # Structure : pending_removal[user_id] = {
        #    "removed": set(["or", "argent", ...]),
        #    "timestamp": time.time()
        # }
        #
        self.pending_removal = {}

    def get_log_channel(self):
        return self.bot.get_channel(self.log_channel_id)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # On identifie les rôles avant/après qui font partie des rangs Valorant
        old_ranks = {r.name.lower() for r in before.roles if r.name != "@everyone" and r.name.lower() in ROLE_RANK}
        new_ranks = {r.name.lower() for r in after.roles  if r.name != "@everyone" and r.name.lower() in ROLE_RANK}

        # Les rôles supprimés (ex: {"or"})
        removed = old_ranks - new_ranks
        # Les rôles ajoutés (ex: {"platine"})
        added   = new_ranks - old_ranks

        # Cas 1 : il y a un retrait d'un ou plusieurs rôles
        if removed:
            # On mémorise qu'on a retiré ces rôles pour ce user
            self.pending_removal[after.id] = {
                "removed": removed,
                "timestamp": time.time()
            }
            # On déclenche la « finalisation » dans 2s
            # (si entre-temps on reçoit un ajout pour ce même user, on l'interceptera)
            asyncio.create_task(self._finalize_removal(after))

        # Cas 2 : il y a un ajout
        if added:
            # Voyons si on avait un retrait en attente pour ce user
            if after.id in self.pending_removal:
                data = self.pending_removal[after.id]
                old_removed = data["removed"]  # set(...)
                # On considère le cas simple : 1 rôle retiré et 1 rôle ajouté
                # (si tu peux retirer plusieurs rangs ou en ajouter plusieurs, il faudra adapter)
                if len(old_removed) == 1 and len(added) == 1:
                    old_rank = list(old_removed)[0]
                    new_rank = list(added)[0]

                    # On efface le "pending removal", on ne veut pas le message "rôle perdu"
                    del self.pending_removal[after.id]

                    # On envoie un message de transition old_rank -> new_rank
                    await self._send_rank_change_message(
                        member=after,
                        old_rank=old_rank,
                        new_rank=new_rank
                    )
                    return
                # Sinon, cas plus complexe (plusieurs rôles) => on peut l'ignorer ou gérer autrement

            # Si pas de pending_removal pour ce user, c'est qu'il vient d'obtenir un nouveau rôle
            # sans qu'on en ait retiré un juste avant. Tu peux décider de logguer ou non.
            # Ex. "Le membre vient d'obtenir le rôle 'Platine'"
            # (Code facultatif)
            # log_channel = self.get_log_channel()
            # if log_channel:
            #     for rank_added in added:
            #         await log_channel.send(
            #             f"{after.mention} a reçu un nouveau rang **{rank_added.capitalize()}**."
            #         )

    async def _finalize_removal(self, member: discord.Member, delay: float = 2.0):
        """Attend quelques secondes pour voir si un nouveau rôle arrive.
           Si rien n'arrive, on finalise le retrait."""
        await asyncio.sleep(delay)

        # Vérifie si le retrait est toujours en attente (et pas 'annulé' par un ajout)
        if member.id in self.pending_removal:
            data = self.pending_removal[member.id]
            # Vérifie qu'on est bien assez "vieux" (pas une màj plus récente)
            if time.time() - data["timestamp"] >= delay:
                # Personne n'a ajouté de nouveau rôle => on logge la perte
                removed_ranks = data["removed"]
                del self.pending_removal[member.id]

                # Exemple de message "User a perdu le rôle X" 
                #log_channel = self.get_log_channel()
                #if log_channel:
                   # for r in removed_ranks:
                        #await log_channel.send(
                       #     f"{member.mention} a perdu son rang **{r.capitalize()}**."
                       # )

    async def _send_rank_change_message(self, member: discord.Member, old_rank: str, new_rank: str):
        """Envoie un message de promotion/rétrogradation unique."""
        log_channel = self.get_log_channel()
        if not log_channel:
            return

        old_val = ROLE_RANK[old_rank]
        new_val = ROLE_RANK[new_rank]
        if new_val < old_val:
            # Promotion
            msg = f"{member.mention} vient de passer **{new_rank.capitalize()}**. Bien joué !"
        else:
            # Rétrogradation
            msg = f"{member.mention} a derank **{new_rank.capitalize()}**. Force à toi !"

        await log_channel.send(msg)

async def setup(bot):
    await bot.add_cog(RoleChangeCog(bot))
