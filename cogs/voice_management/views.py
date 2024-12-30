# cogs\voice_management\views.py

import discord
from discord.ui import View, Button, Modal, TextInput
from typing import List, Optional
import logging
from cogs.voice_management.services.five_stack_service import MatchmakingService

logger = logging.getLogger("five_stack")


class QueueView(View):
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

        # Ajouter les boutons Solo et Équipe avec des IDs persistants
        self.add_item(self.create_solo_button())
        self.add_item(self.create_team_button())

    def create_solo_button(self):
        button = Button(label="Solo", style=discord.ButtonStyle.primary, custom_id=f"solo_button_{self.guild_id}")
        button.callback = self.solo_button_callback
        return button

    def create_team_button(self):
        button = Button(label="Équipe", style=discord.ButtonStyle.secondary, custom_id=f"team_button_{self.guild_id}")
        button.callback = self.team_button_callback
        return button

    async def solo_button_callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            user = interaction.user

            server_id = await MatchmakingService.get_server_id(self.guild_id)
            if not server_id:
                await interaction.followup.send("Erreur : Serveur non configuré.", ephemeral=True)
                return

            if await self.cog.is_user_banned(user, server_id):
                await interaction.followup.send("Vous ne pouvez pas rejoindre la queue car vous avez le rôle 'ban'.", ephemeral=True)
                return

            user_info = await self.cog.MatchmakingService.get_user_info(user.id)
            if not user_info:
                await interaction.followup.send("Erreur : Impossible de récupérer vos informations Valorant.", ephemeral=True)
                return

            member = interaction.guild.get_member(user.id)
            if not member:
                await interaction.followup.send("Erreur : Membre introuvable dans le serveur.", ephemeral=True)
                return

            role_name = await self.cog.get_user_primary_role(member, server_id)
            language = await self.cog.get_user_language(member, server_id)

            if not language:
                await interaction.followup.send("Erreur : Vous devez avoir un rôle de langue (français, anglais, espagnol).", ephemeral=True)
                return

            solo_entry = {
                "type": "solo",
                "discord_member": member,
                "region": user_info["region"],
                "elo": user_info["elo"],
                "mmr_average": user_info["elo"],
                "mmr_low": user_info["elo"],
                "mmr_high": user_info["elo"],
                "roles": [role_name],
                "language": language,
            }

            await self.cog.add_to_main_queue(solo_entry)
            await interaction.followup.send("Vous avez été ajouté à la queue Solo!", ephemeral=True)
            await self.cog.update_queue_status_embed(self.guild_id)

        except Exception as e:
            logger.error(f"Erreur inattendue dans solo_button_callback : {e}")
            await interaction.followup.send("Une erreur inattendue s'est produite.", ephemeral=True)

    async def team_button_callback(self, interaction: discord.Interaction):
        server_id = await MatchmakingService.get_server_id(self.guild_id)
        if not server_id:
            await interaction.response.send_message("Erreur : Serveur non configuré.", ephemeral=True)
            return
        await interaction.response.send_modal(TeamModal(self.cog, self.guild_id, server_id))


class TeamModal(Modal):
    def __init__(self, cog, guild_id: int, server_id: int):
        super().__init__(title="Créer une Équipe")
        self.cog = cog
        self.guild_id = guild_id
        self.server_id = server_id

        self.member1 = TextInput(label="Membre 1 (ID ou mention)", required=True, max_length=100)
        self.member2 = TextInput(label="Membre 2 (ID ou mention)", required=True, max_length=100)
        self.member3 = TextInput(label="Membre 3 (Optionnel)", required=False, max_length=100)
        self.member4 = TextInput(label="Membre 4 (Optionnel)", required=False, max_length=100)

        self.add_item(self.member1)
        self.add_item(self.member2)
        self.add_item(self.member3)
        self.add_item(self.member4)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Différer la réponse pour éviter que l'interaction n'expire
            await interaction.response.defer(ephemeral=True)

            leader = interaction.user
            member_inputs = [self.member1.value, self.member2.value]
            if self.member3.value:
                member_inputs.append(self.member3.value)
            if self.member4.value:
                member_inputs.append(self.member4.value)

            success, message = await self.cog.create_team(leader, member_inputs, self.server_id)
            if success:
                await interaction.followup.send("Équipe créée et ajoutée à la queue!", ephemeral=True)
                await self.cog.update_queue_status_embed(self.guild_id)
            else:
                await interaction.followup.send(f"Erreur: {message}", ephemeral=True)
        except Exception as e:
            logger.error(f"Erreur inattendue dans on_submit : {e}")
            try:
                await interaction.followup.send("Une erreur inattendue s'est produite.", ephemeral=True)
            except Exception:
                pass