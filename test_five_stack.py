import asyncio
from asyncio.log import logger
from collections import deque
import datetime
from discord import Embed
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from cogs.voice_management.five_stack import Matchmaking
from cogs.voice_management.views import QueueView

@pytest.mark.asyncio
async def test_is_user_banned_true():
    # Mock du rôle "ban"
    mock_role = MagicMock(id=123)
    mock_member = MagicMock()
    mock_member.roles = [mock_role]
    mock_member.guild.roles = [mock_role]

    with patch("cogs.voice_management.services.five_stack_service.MatchmakingService.get_role_id", new=AsyncMock(return_value=123)):
        bot = MagicMock()
        cog = Matchmaking(bot)
        result = await cog.is_user_banned(mock_member, 42)
        assert result is True  # L'utilisateur est banni

@pytest.mark.asyncio
async def test_is_user_banned_false():
    # Mock sans le rôle "ban"
    mock_role = MagicMock(id=124)
    mock_member = MagicMock()
    mock_member.roles = [mock_role]
    mock_member.guild.roles = [mock_role]

    with patch("cogs.voice_management.services.five_stack_service.MatchmakingService.get_role_id", new=AsyncMock(return_value=123)):
        bot = MagicMock()
        cog = Matchmaking(bot)
        result = await cog.is_user_banned(mock_member, 42)
        assert result is False  # L'utilisateur n'est pas banni

@pytest.mark.asyncio
async def test_is_user_banned_no_ban_role():
    # Cas où le rôle "ban" n'existe pas
    mock_member = MagicMock()
    mock_member.roles = []
    mock_member.guild.roles = []

    with patch("cogs.voice_management.services.five_stack_service.MatchmakingService.get_role_id", new=AsyncMock(return_value=None)):
        bot = MagicMock()
        cog = Matchmaking(bot)
        result = await cog.is_user_banned(mock_member, 42)
        assert result is False  # Aucun rôle "ban"

@pytest.mark.asyncio
async def test_is_user_banned_error():
    # Cas où une exception est levée lors de la récupération du rôle "ban"
    mock_member = MagicMock()
    mock_member.roles = []

    with patch("cogs.voice_management.services.five_stack_service.MatchmakingService.get_role_id", new=AsyncMock(side_effect=Exception("Database error"))):
        bot = MagicMock()
        cog = Matchmaking(bot)
        result = await cog.is_user_banned(mock_member, 42)
        assert result is False  # Exception gérée correctement

@pytest.mark.asyncio
async def test_get_user_primary_role_found():
    # Mock des rôles du serveur
    mock_roles = {"duelist": 1, "sentinel": 2, "controller": 3}
    mock_role = MagicMock(id=2)
    mock_role.name = "Sentinel"
    mock_member = MagicMock()
    mock_member.roles = [mock_role]

    with patch("cogs.voice_management.services.five_stack_service.MatchmakingService.get_role_ids", new=AsyncMock(return_value=mock_roles)):
        bot = MagicMock()
        cog = Matchmaking(bot)
        result = await cog.get_user_primary_role(mock_member, 42)
        assert result == "sentinel"  # Le rôle principal doit être "sentinel"


@pytest.mark.asyncio
async def test_get_user_primary_role_fill():
    # Mock des rôles du serveur sans correspondance
    mock_roles = {"duelist": 1, "sentinel": 2, "controller": 3}
    mock_role = MagicMock(id=999, name="RandomRole")
    mock_member = MagicMock()
    mock_member.roles = [mock_role]

    with patch("cogs.voice_management.services.five_stack_service.MatchmakingService.get_role_ids", new=AsyncMock(return_value=mock_roles)):
        bot = MagicMock()
        cog = Matchmaking(bot)
        result = await cog.get_user_primary_role(mock_member, 42)
        assert result == "fill"  # Aucun rôle principal trouvé, retourne 'fill'

@pytest.mark.asyncio
async def test_get_user_primary_role_error():
    # Cas où une erreur survient lors de la récupération des rôles
    mock_member = MagicMock()
    mock_member.roles = []

    with patch("cogs.voice_management.services.five_stack_service.MatchmakingService.get_role_ids", new=AsyncMock(side_effect=Exception("Database error"))):
        bot = MagicMock()
        cog = Matchmaking(bot)
        result = await cog.get_user_primary_role(mock_member, 42)
        assert result == "fill"  # En cas d'erreur, retourne 'fill'

@pytest.mark.asyncio
async def test_get_user_language_found():
    # Mock des rôles linguistiques
    mock_language_roles = {"francais": 1, "anglais": 2, "espagnol": 3}
    mock_role = MagicMock(id=2)
    mock_member = MagicMock()
    mock_member.roles = [mock_role]

    with patch("cogs.voice_management.services.five_stack_service.MatchmakingService.get_language_roles", new=AsyncMock(return_value=mock_language_roles)):
        with patch("discord.utils.get", return_value=mock_role):
            bot = MagicMock()
            cog = Matchmaking(bot)
            result = await cog.get_user_language(mock_member, 42)
            assert result == "anglais"  # La langue doit être 'anglais'

@pytest.mark.asyncio
async def test_get_user_language_found():
    # Mock des rôles linguistiques
    mock_language_roles = {"francais": 1, "anglais": 2, "espagnol": 3}
    mock_role = MagicMock(id=2)  # Rôle correspondant à "anglais"
    mock_member = MagicMock()
    mock_member.roles = [mock_role]

    with patch("cogs.voice_management.services.five_stack_service.MatchmakingService.get_language_roles", new=AsyncMock(return_value=mock_language_roles)):
        with patch("discord.utils.get", side_effect=lambda roles, id: mock_role if id == 2 else None):
            bot = MagicMock()
            cog = Matchmaking(bot)
            result = await cog.get_user_language(mock_member, 42)
            assert result == "anglais"  # La langue doit être 'anglais'

@pytest.mark.asyncio
async def test_get_user_language_error():
    # Cas où une erreur survient lors de la récupération des rôles linguistiques
    mock_member = MagicMock()
    mock_member.roles = []

    with patch("cogs.voice_management.services.five_stack_service.MatchmakingService.get_language_roles", new=AsyncMock(side_effect=Exception("Database error"))):
        bot = MagicMock()
        cog = Matchmaking(bot)
        result = await cog.get_user_language(mock_member, 42)
        assert result is None  # En cas d'erreur, retourne None

@pytest.mark.asyncio
async def test_add_to_main_queue_solo():
    # Mock un joueur solo
    mock_member = MagicMock()
    mock_member.display_name = "Player1"
    entry = {
        "type": "solo",
        "discord_member": mock_member
    }

    bot = MagicMock()
    cog = Matchmaking(bot)
    cog.main_queue = deque()  # Initialise la file d'attente

    with patch("logging.Logger.info") as mock_logger:
        await cog.add_to_main_queue(entry)

        # Vérifie que l'entrée est ajoutée à la file d'attente
        assert len(cog.main_queue) == 1
        assert cog.main_queue[0] == entry

        # Vérifie que le log est correctement généré
        mock_logger.assert_called_once_with("Entrée ajoutée à la queue : solo - Player1")

@pytest.mark.asyncio
async def test_add_to_main_queue_team():
    # Mock une équipe
    mock_member1 = MagicMock()
    mock_member1.display_name = "Player1"
    mock_member2 = MagicMock()
    mock_member2.display_name = "Player2"
    entry = {
        "type": "team",
        "discord_members": [mock_member1, mock_member2]
    }

    bot = MagicMock()
    cog = Matchmaking(bot)
    cog.main_queue = deque()  # Initialise la file d'attente

    with patch("logging.Logger.info") as mock_logger:
        await cog.add_to_main_queue(entry)

        # Vérifie que l'entrée est ajoutée à la file d'attente
        assert len(cog.main_queue) == 1
        assert cog.main_queue[0] == entry

        # Vérifie que le log est correctement généré
        mock_logger.assert_called_once_with("Entrée ajoutée à la queue : team - Player1, Player2")

@pytest.mark.asyncio
async def test_add_to_main_queue_missing_type():
    # Mock une entrée sans type
    entry = {
        "discord_member": MagicMock()
    }

    bot = MagicMock()
    cog = Matchmaking(bot)
    cog.main_queue = deque()  # Initialise la file d'attente

    with patch("logging.Logger.info") as mock_logger:
        with pytest.raises(KeyError):  # Vérifie que KeyError est levée
            await cog.add_to_main_queue(entry)

        # Vérifie que rien n'est ajouté à la file d'attente
        assert len(cog.main_queue) == 0

        # Vérifie que le log n'est pas généré
        mock_logger.assert_not_called()

@pytest.mark.asyncio
async def test_update_queue_status_embed_success():
    # Mock des données de la file d'attente
    mock_channel = MagicMock()
    mock_message = MagicMock()
    mock_embed = MagicMock()
    mock_view = MagicMock()

    with patch("cogs.voice_management.five_stack.Matchmaking.create_queue_embed", new=AsyncMock(return_value=mock_embed)):
        with patch("cogs.voice_management.five_stack.QueueView", return_value=mock_view):
            bot = MagicMock()
            cog = Matchmaking(bot)
            cog.queue_status_embed_message = {42: (123, 456)}
            bot.get_channel = MagicMock(return_value=mock_channel)
            mock_channel.fetch_message = AsyncMock(return_value=mock_message)

            await cog.update_queue_status_embed(42)

            # Vérifie que le message est mis à jour avec le bon embed et vue
            mock_message.edit.assert_called_once_with(embed=mock_embed, view=mock_view)

@pytest.mark.asyncio
async def test_update_queue_status_embed_missing_message():
    bot = MagicMock()
    cog = Matchmaking(bot)
    cog.queue_status_embed_message = {}  # Aucun message persistant configuré

    with patch("logging.Logger.warning") as mock_logger:
        await cog.update_queue_status_embed(42)

        # Vérifie qu'un avertissement est logué
        mock_logger.assert_called_once_with("Aucun message persistant trouvé pour guild_id 42.")

@pytest.mark.asyncio
async def test_update_queue_status_embed_missing_channel():
    bot = MagicMock()
    cog = Matchmaking(bot)
    cog.queue_status_embed_message = {42: (123, 456)}
    bot.get_channel = MagicMock(return_value=None)  # Le salon est introuvable

    with patch("logging.Logger.error") as mock_logger:
        await cog.update_queue_status_embed(42)

        # Vérifie qu'une erreur est loguée
        mock_logger.assert_called_once_with("Channel ID 123 introuvable pour guild_id 42.")

@pytest.mark.asyncio
async def test_update_queue_status_embed_exception():
    # Simule une exception lors de l'édition du message
    mock_channel = MagicMock()
    mock_channel.fetch_message = AsyncMock(side_effect=Exception("Fetch message error"))

    bot = MagicMock()
    cog = Matchmaking(bot)
    cog.queue_status_embed_message = {42: (123, 456)}
    bot.get_channel = MagicMock(return_value=mock_channel)

    with patch("logging.Logger.error") as mock_logger:
        await cog.update_queue_status_embed(42)

        # Vérifie qu'une erreur spécifique est loguée
        mock_logger.assert_any_call(
            "Erreur lors de la mise à jour de l'embed de la queue pour guild_id 42 : Fetch message error"
        )

@pytest.mark.asyncio
async def test_create_voice_channel_success():
    mock_guild = MagicMock()
    mock_category = MagicMock()
    mock_channel = AsyncMock()  # Utilise AsyncMock ici

    # Simule la catégorie existante
    mock_guild.categories = [mock_category]
    mock_category.name = "Matchs en cours"

    # Simule la création du salon vocal
    mock_guild.create_voice_channel = AsyncMock(return_value=mock_channel)

    # Simule les membres du groupe
    mock_member1 = MagicMock()
    mock_member1.guild = mock_guild
    mock_member1.move_to = AsyncMock()
    mock_member2 = MagicMock()
    mock_member2.guild = mock_guild
    mock_member2.move_to = AsyncMock()

    bot = MagicMock()
    cog = Matchmaking(bot)

    await cog.create_voice_channel([mock_member1, mock_member2])

    # Vérifie que le salon vocal est créé
    mock_guild.create_voice_channel.assert_called_once()

    # Vérifie que les membres sont déplacés
    mock_member1.move_to.assert_called_once_with(mock_channel)
    mock_member2.move_to.assert_called_once_with(mock_channel)


@pytest.mark.asyncio
async def test_create_voice_channel_missing_category():
    mock_guild = MagicMock()
    mock_category = MagicMock()
    mock_channel = AsyncMock()  # Utilise AsyncMock ici

    # Simule l'absence de catégorie
    mock_guild.categories = []
    mock_guild.create_category = AsyncMock(return_value=mock_category)

    # Simule la création du salon vocal
    mock_guild.create_voice_channel = AsyncMock(return_value=mock_channel)

    # Simule les membres du groupe
    mock_member = MagicMock()
    mock_member.guild = mock_guild
    mock_member.move_to = AsyncMock()

    bot = MagicMock()
    cog = Matchmaking(bot)

    await cog.create_voice_channel([mock_member])

    # Vérifie que la catégorie est créée
    mock_guild.create_category.assert_called_once_with("Matchs en cours")


@pytest.mark.asyncio
async def test_create_voice_channel_member_move_error():
    mock_guild = MagicMock()
    mock_channel = AsyncMock()

    # Simule la création du salon vocal
    mock_guild.create_voice_channel = AsyncMock(return_value=mock_channel)

    # Simule un membre avec une erreur de déplacement
    mock_member = MagicMock()
    mock_member.guild = mock_guild
    mock_member.move_to = AsyncMock(side_effect=Exception("Move error"))

    bot = MagicMock()
    cog = Matchmaking(bot)

    # Annuler et attendre la fin de la tâche de fond
    cog.process_queue_task_loop.cancel()
    await asyncio.sleep(0)  # Permet de traiter l'annulation

    with patch("logging.Logger.error") as mock_logger:
        await cog.create_voice_channel([mock_member])

        # Filtrez les appels au logger pour vérifier uniquement l'erreur de déplacement
        mock_logger.assert_any_call(f"Erreur lors du déplacement de {mock_member.display_name} : Move error")

        # Vérifie que le logger a été appelé au moins une fois pour cette erreur spécifique
        assert any("Erreur lors du déplacement" in call.args[0] for call in mock_logger.call_args_list)

@pytest.mark.asyncio
async def test_find_matching_group_success():
    bot = MagicMock()
    cog = Matchmaking(bot)

    # Simule une file d'attente avec des joueurs compatibles
    cog.main_queue = deque([
        {"type": "solo", "discord_member": MagicMock(), "mmr_average": 1000, "mmr_low": 950, "mmr_high": 1050, "region": "EU", "language": "anglais", "roles": ["duelist"]},
        {"type": "solo", "discord_member": MagicMock(), "mmr_average": 1005, "mmr_low": 960, "mmr_high": 1050, "region": "EU", "language": "anglais", "roles": ["sentinel"]},
        {"type": "team", "discord_members": [MagicMock(), MagicMock()], "mmr_average": 1002, "mmr_low": 995, "mmr_high": 1010, "region": "EU", "language": "anglais", "roles": ["controller", "fill"]},
        {"type": "solo", "discord_member": MagicMock(), "mmr_average": 1001, "mmr_low": 990, "mmr_high": 1010, "region": "EU", "language": "anglais", "roles": ["initiator"]},
        {"type": "solo", "discord_member": MagicMock(), "mmr_average": 1003, "mmr_low": 980, "mmr_high": 1020, "region": "EU", "language": "anglais", "roles": ["fill"]},
    ])

    group = await cog.find_matching_group()

    # Vérifie qu'un groupe est trouvé
    assert group is not None, "Expected a group, but got None"
    assert len(group) == 5
    assert all(isinstance(member, MagicMock) for member in group)


@pytest.mark.asyncio
async def test_find_matching_group_no_match():
    bot = MagicMock()
    cog = Matchmaking(bot)

    # Simule une file d'attente sans joueurs compatibles
    cog.main_queue = deque([
        {"type": "solo", "discord_member": MagicMock(), "mmr_average": 1000, "mmr_low": 950, "mmr_high": 1050, "region": "NA", "language": "anglais", "roles": ["duelist"]},
        {"type": "solo", "discord_member": MagicMock(), "mmr_average": 2000, "mmr_low": 1950, "mmr_high": 2050, "region": "EU", "language": "francais", "roles": ["sentinel"]}
    ])

    group = await cog.find_matching_group()

    # Vérifie qu'aucun groupe n'est trouvé
    assert group is None

@pytest.mark.asyncio
async def test_find_matching_group_invalid_entry():
    bot = MagicMock()
    cog = Matchmaking(bot)

    # Simule une file d'attente avec une entrée invalide
    cog.main_queue = deque([
        {"type": "solo", "discord_member": MagicMock(), "mmr_average": 1000, "mmr_low": 950, "mmr_high": 1050, "region": "EU", "language": "anglais", "roles": ["duelist"]},
        {"type": "invalid", "discord_member": MagicMock()}  # Entrée invalide
    ])

    # Vérifie que la fonction ne lève pas d'exception
    group = await cog.find_matching_group()
    assert group is None  # Aucun groupe ne doit être formé

@pytest.mark.asyncio
async def test_update_queue_status_embed_success():
    bot = MagicMock()
    cog = Matchmaking(bot)

    # Mock le message persistant
    mock_channel = MagicMock()
    mock_message = AsyncMock()

    mock_channel.fetch_message = AsyncMock(return_value=mock_message)
    bot.get_channel = MagicMock(return_value=mock_channel)

    # Ajoute une entrée dans queue_status_embed_message
    guild_id = 12345
    cog.queue_status_embed_message[guild_id] = (67890, 54321)

    # Mock create_queue_embed et QueueView
    cog.create_queue_embed = AsyncMock(return_value=MagicMock())
    with patch("cogs.voice_management.five_stack.QueueView", return_value=MagicMock()):
        await cog.update_queue_status_embed(guild_id)

        # Vérifie que le channel et le message sont bien récupérés
        bot.get_channel.assert_called_once_with(67890)
        mock_channel.fetch_message.assert_called_once_with(54321)

        # Vérifie que le message est mis à jour avec un nouvel embed et une vue
        mock_message.edit.assert_called_once()
        args, kwargs = mock_message.edit.call_args
        assert "embed" in kwargs
        assert "view" in kwargs

@pytest.mark.asyncio
async def test_create_queue_embed():
    bot = MagicMock()
    cog = Matchmaking(bot)

    guild_id = 12345

    # Mock les données de la queue
    cog.main_queue = [
        {"type": "solo", "language": "anglais"},
        {"type": "team", "language": "anglais", "discord_members": [MagicMock(), MagicMock()]},
        {"type": "solo", "language": "anglais"}
    ]
    cog.last_match_time[guild_id] = datetime.datetime.utcnow() - datetime.timedelta(seconds=15)

    # Appelle la fonction
    embed = await cog.create_queue_embed(guild_id)

    # Vérifie que l'embed est correctement créé
    assert isinstance(embed, Embed)
    assert "Rejoignez la Queue Valorant" in embed.title
    assert embed.fields[0].name == "Solo en Attente"
    assert embed.fields[0].value == "2"  # Deux entrées solo
    assert embed.fields[1].name == "Équipes en Attente"
    assert embed.fields[1].value == "1"  # Une équipe
    assert embed.fields[2].name == "Membres Totaux"
    assert embed.fields[2].value == "4"  # Deux solos + deux membres d'équipe
    assert embed.fields[3].name == "Prochain Match"
    assert embed.fields[3].value == "Disponible maintenant" or ":" in embed.fields[3].value

@pytest.mark.asyncio
async def test_setup_voice_view():
    bot = MagicMock()
    cog = Matchmaking(bot)

    # Mock des messages persistants
    guild_id = 12345
    cog.queue_status_embed_message[guild_id] = (67890, 54321)

    mock_channel = MagicMock()
    mock_message = AsyncMock()
    bot.get_channel = MagicMock(return_value=mock_channel)
    mock_channel.fetch_message = AsyncMock(return_value=mock_message)

    with patch("cogs.voice_management.five_stack.QueueView", return_value=MagicMock()) as mock_view:
        await cog.setup_voice_view(guild_id)

        # Vérifie que le channel et le message sont bien récupérés
        bot.get_channel.assert_called_once_with(67890)
        mock_channel.fetch_message.assert_called_once_with(54321)

        # Vérifie que le message est mis à jour avec une nouvelle vue
        mock_message.edit.assert_called_once()
        args, kwargs = mock_message.edit.call_args
        assert "view" in kwargs

@pytest.mark.asyncio
async def test_create_team_success():
    bot = MagicMock()
    cog = Matchmaking(bot)

    mock_leader = MagicMock()
    mock_leader.display_name = "Leader"
    mock_leader.guild = MagicMock()
    mock_member1 = MagicMock()
    mock_member1.id = 1
    mock_member1.display_name = "Member1"
    mock_member2 = MagicMock()
    mock_member2.id = 2
    mock_member2.display_name = "Member2"

    mock_members = [mock_leader, mock_member1, mock_member2]
    mock_leader.guild.get_member = MagicMock(side_effect=lambda x: mock_members[x])

    with patch("cogs.voice_management.services.five_stack_service.MatchmakingService.get_user_info", new_callable=AsyncMock, side_effect=[
        {"region": "EU", "elo": 1050},  # Leader
        {"region": "EU", "elo": 1000},  # Member 1
        {"region": "EU", "elo": 1020}   # Member 2
    ]) as mock_get_user_info, \
         patch("cogs.voice_management.five_stack.Matchmaking.is_user_banned", return_value=False), \
         patch("cogs.voice_management.five_stack.Matchmaking.get_user_primary_role", side_effect=["duelist", "initiator", "sentinel"]), \
         patch("cogs.voice_management.five_stack.Matchmaking.get_user_language", return_value="anglais"), \
         patch("cogs.voice_management.five_stack.Matchmaking.add_to_main_queue") as mock_add_to_main_queue:

        success, message = await cog.create_team(mock_leader, ["<@1>", "<@2>"], 42)

        # Vérifications des résultats
        mock_get_user_info.assert_any_call(mock_member1.id)
        mock_get_user_info.assert_any_call(mock_member2.id)
        mock_add_to_main_queue.assert_called_once()
        assert success is True, f"Test échoué, message reçu : {message}"

@pytest.mark.asyncio
async def test_process_queue_task_loop():
    bot = MagicMock()
    cog = Matchmaking(bot)

    # Mocks pour les membres
    member1 = MagicMock(display_name="User1")
    member2 = MagicMock(display_name="User2")
    member3 = MagicMock(display_name="User3")
    member4 = MagicMock(display_name="User4")
    member5 = MagicMock(display_name="User5")

    # Mock des données dans la queue
    cog.main_queue = deque([
        {"type": "solo", "discord_member": member1, "mmr_average": 1000, "region": "EU", "language": "anglais"},
        {"type": "solo", "discord_member": member2, "mmr_average": 1005, "region": "EU", "language": "anglais"},
        {"type": "team", "discord_members": [member3, member4], "mmr_average": 1002, "region": "EU", "language": "anglais"}
    ])

    cog.queue_status_embed_message = {12345: (67890, 54321)}
    cog.create_voice_channel = AsyncMock(return_value="MockChannel")
    cog.find_matching_group = AsyncMock(side_effect=[
        [member1, member2, member3, member4, member5],  # Groupe valide
        None  # Aucun groupe trouvé après la première itération
    ])

    with patch("cogs.voice_management.five_stack.Matchmaking.update_queue_status_embed", new_callable=AsyncMock):
        await cog.process_queue_task_loop()

        # Vérifie que la fonction crée un salon vocal
        cog.create_voice_channel.assert_called_once_with([
            member1, member2, member3, member4, member5
        ])

@pytest.mark.asyncio
async def test_load_persistent_messages():
    bot = MagicMock()
    cog = Matchmaking(bot)

    # Mock des données récupérées depuis la base de données
    mock_rows = [{"guild_id": 1, "channel_id": 2, "message_id": 3}]
    mock_message = MagicMock(id=3)
    mock_channel = MagicMock(fetch_message=AsyncMock(return_value=mock_message))
    mock_guild = MagicMock(get_channel=MagicMock(return_value=mock_channel))
    bot.get_guild = MagicMock(return_value=mock_guild)

    with patch("utils.database.database.fetch", new=AsyncMock(return_value=mock_rows)), \
         patch("cogs.voice_management.five_stack.QueueView", return_value=MagicMock()):
        await cog.load_persistent_messages()

        # Vérifie que les messages sont correctement chargés
        assert 1 in cog.queue_status_embed_message
        assert cog.queue_status_embed_message[1] == (2, 3)

@pytest.mark.asyncio
async def test_create_voice_channel_permissions():
    mock_guild = MagicMock()
    mock_category = MagicMock()
    mock_channel = AsyncMock()
    mock_guild.categories = [mock_category]
    mock_category.name = "Matchs en cours"
    mock_guild.create_voice_channel = AsyncMock(return_value=mock_channel)

    mock_member = MagicMock()
    mock_member.guild = mock_guild
    mock_member.move_to = AsyncMock()

    bot = MagicMock()
    cog = Matchmaking(bot)

    await cog.create_voice_channel([mock_member])
    mock_channel.edit.assert_called_once()
    mock_member.move_to.assert_called_once_with(mock_channel)

@pytest.mark.asyncio
async def test_load_persistent_messages_error_handling():
    bot = MagicMock()
    cog = Matchmaking(bot)

    # Mock pour simuler une exception lors de fetch_message
    mock_channel = MagicMock(fetch_message=AsyncMock(side_effect=Exception("Fetch error")))
    mock_guild = MagicMock(get_channel=MagicMock(return_value=mock_channel))
    bot.get_guild = MagicMock(return_value=mock_guild)

    with patch("utils.database.database.fetch", return_value=[{"guild_id": 1, "channel_id": 2, "message_id": 3}]), \
         patch("cogs.voice_management.five_stack.logger") as mock_logger:
        
        await cog.load_persistent_messages()

        # Vérifie que l'erreur est loggée
        mock_logger.error.assert_any_call("Erreur lors du chargement du message pour guild_id 1: Fetch error")

@pytest.mark.asyncio
async def test_cog_unload():
    bot = MagicMock()
    cog = Matchmaking(bot)
    cog.cog_unload()
    await asyncio.sleep(0)  # Laisser le temps à l'annulation d'être traitée
    assert cog.process_queue_task_loop._task.cancelled(), "La tâche n'a pas été annulée correctement."

@pytest.mark.asyncio
async def test_on_ready():
    bot = MagicMock()
    cog = Matchmaking(bot)
    with patch.object(cog, 'load_persistent_messages', new_callable=AsyncMock) as mock_load:
        await cog.on_ready()
        mock_load.assert_called_once()

@pytest.mark.asyncio
async def test_start_queue():
    bot = MagicMock()
    cog = Matchmaking(bot)
    mock_ctx = MagicMock()
    mock_ctx.guild.id = 42
    mock_ctx.send = AsyncMock()  # Simule l'envoi d'un message

    with patch("cogs.voice_management.services.five_stack_service.MatchmakingService.get_server_id", new_callable=AsyncMock, return_value=42), \
         patch("cogs.voice_management.five_stack.Matchmaking.create_queue_embed", new_callable=AsyncMock, return_value=MagicMock()), \
         patch("cogs.voice_management.five_stack.QueueView", return_value=MagicMock()):
        # Utilisez la commande via son invocation
        await cog.start_queue.callback(cog, mock_ctx)

        # Vérifiez qu'un message a été envoyé
        mock_ctx.send.assert_called_once()

def test_get_queue_language():
    bot = MagicMock()
    with patch("cogs.voice_management.five_stack.Matchmaking.process_queue_task_loop", new_callable=MagicMock):
        cog = Matchmaking(bot)

    # Mock les données de la file d'attente
    cog.main_queue = [
        {"language": "anglais"},
        {"language": "anglais"}
    ]
    assert cog.get_queue_language(42) == "anglais"

    cog.main_queue.append({"language": "francais"})
    assert cog.get_queue_language(42) == "mixte"
