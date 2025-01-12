import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from discord import Interaction, Member
from cogs.voice_management.queue_views import QueueView, TeamModal


@pytest.mark.asyncio
async def test_queue_view_solo_button_callback():
    # Mock interaction et utilisateur
    mock_user = MagicMock()
    mock_member = MagicMock()
    mock_member.id = mock_user.id
    mock_interaction = MagicMock()
    mock_interaction.user = mock_user
    mock_interaction.guild.get_member = MagicMock(return_value=mock_member)
    mock_interaction.response.defer = AsyncMock()
    mock_interaction.followup.send = AsyncMock()

    # Mock des services et du cog
    mock_cog = MagicMock()
    mock_cog.MatchmakingService.get_server_id = AsyncMock(return_value=42)
    mock_cog.is_user_banned = AsyncMock(return_value=False)
    mock_cog.MatchmakingService.get_user_info = AsyncMock(return_value={"region": "EU", "elo": 1000})
    mock_cog.get_user_primary_role = AsyncMock(return_value="duelist")
    mock_cog.get_user_language = AsyncMock(return_value="anglais")
    mock_cog.add_to_main_queue = AsyncMock()
    mock_cog.update_queue_status_embed = AsyncMock()

    # Créer une instance de QueueView
    queue_view = QueueView(mock_cog, guild_id=123)

    # Appeler le callback
    solo_button = queue_view.create_solo_button()
    await solo_button.callback(mock_interaction)

    # Assertions sur les appels
    mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
    mock_cog.MatchmakingService.get_server_id.assert_called_once_with(123)
    mock_cog.is_user_banned.assert_called_once_with(mock_user, 42)
    mock_cog.MatchmakingService.get_user_info.assert_called_once_with(mock_user.id)
    mock_cog.add_to_main_queue.assert_called_once()
    mock_interaction.followup.send.assert_called_once_with("Vous avez été ajouté à la queue Solo!", ephemeral=True)


@pytest.mark.asyncio
async def test_queue_view_team_button_callback():
    # Mock interaction
    mock_interaction = MagicMock()
    mock_interaction.response.send_modal = AsyncMock()

    # Mock des services et du cog
    mock_cog = MagicMock()
    mock_cog.MatchmakingService.get_server_id = AsyncMock(return_value=42)

    # Créer une instance de QueueView
    queue_view = QueueView(mock_cog, guild_id=123)

    # Appeler le callback
    team_button = queue_view.create_team_button()
    await team_button.callback(mock_interaction)

    # Assertions sur les appels
    mock_cog.MatchmakingService.get_server_id.assert_called_once_with(123)
    mock_interaction.response.send_modal.assert_called_once()

@pytest.mark.asyncio
async def test_team_modal_on_submit_success():
    # Mock interaction
    mock_interaction = MagicMock()
    mock_interaction.user = MagicMock()
    mock_interaction.response.send_message = AsyncMock()

    # Mock du cog
    mock_cog = MagicMock()
    mock_cog.create_team = AsyncMock(return_value=(True, "Équipe créée avec succès"))
    mock_cog.update_queue_status_embed = AsyncMock()

    # Mock TextInputs directement
    mock_member1 = MagicMock()
    type(mock_member1).value = PropertyMock(return_value="<@123>")

    mock_member2 = MagicMock()
    type(mock_member2).value = PropertyMock(return_value="<@456>")

    # Créer une instance de TeamModal
    modal = TeamModal(mock_cog, guild_id=123, server_id=42)
    modal.member1 = mock_member1
    modal.member2 = mock_member2

    # Appeler on_submit
    await modal.on_submit(mock_interaction)

    # Assertions
    mock_cog.create_team.assert_called_once_with(mock_interaction.user, ["<@123>", "<@456>"], 42)
    mock_cog.update_queue_status_embed.assert_called_once_with(123)
    mock_interaction.response.send_message.assert_called_once_with("Équipe créée et ajoutée à la queue!", ephemeral=True)

@pytest.mark.asyncio
async def test_team_modal_on_submit_error():
    # Mock interaction
    mock_interaction = MagicMock()
    mock_interaction.user = MagicMock()
    mock_interaction.response.send_message = AsyncMock()

    # Mock du cog
    mock_cog = MagicMock()
    mock_cog.create_team = AsyncMock(return_value=(False, "Erreur lors de la création de l'équipe"))

    # Mock des TextInputs
    mock_member1 = MagicMock()
    type(mock_member1).value = PropertyMock(return_value="<@123>")
    mock_member2 = MagicMock()
    type(mock_member2).value = PropertyMock(return_value="<@456>")

    # Créer une instance de TeamModal
    modal = TeamModal(mock_cog, guild_id=123, server_id=42)
    modal.member1 = mock_member1
    modal.member2 = mock_member2

    # Appeler on_submit
    await modal.on_submit(mock_interaction)

    # Assertions
    mock_cog.create_team.assert_called_once_with(mock_interaction.user, ["<@123>", "<@456>"], 42)
    mock_interaction.response.send_message.assert_called_once_with(
        "Erreur: Erreur lors de la création de l'équipe", ephemeral=True
    )

def test_create_team_call():
    mock_cog = MagicMock()
    mock_cog.create_team = AsyncMock()
    mock_user = MagicMock()
    members = ["<@123>", "<@456>"]
    server_id = 42

    # Appeler create_team directement
    result = mock_cog.create_team(mock_user, members, server_id)

    # Vérifier les arguments
    mock_cog.create_team.assert_called_once_with(mock_user, members, server_id)

@pytest.mark.asyncio
async def test_solo_button_callback_exception():
    mock_cog = MagicMock()
    mock_cog.MatchmakingService.get_server_id.side_effect = Exception("Unexpected error")
    queue_view = QueueView(mock_cog, guild_id=123)
    solo_button = queue_view.create_solo_button()

    mock_interaction = MagicMock()
    mock_interaction.response.defer = AsyncMock()
    mock_interaction.followup.send = AsyncMock()

    await solo_button.callback(mock_interaction)

    # Vérifiez que le message d'erreur est envoyé
    mock_interaction.followup.send.assert_called_once_with(
        "Une erreur inattendue s'est produite.", ephemeral=True
    )
