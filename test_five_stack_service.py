import os
import sys
import pytest
from unittest.mock import AsyncMock, patch
from cogs.voice_management.services.five_stack_service import MatchmakingService

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

@pytest.mark.asyncio
async def test_get_user_info_found():
    # Mock la réponse de la base de données
    mock_row = {"valorant_elo": 1200, "valorant_region": "EU"}
    with patch("utils.database.database.fetchrow", new=AsyncMock(return_value=mock_row)):
        # Appelle la fonction
        result = await MatchmakingService.get_user_info(123456789)
        
        # Vérifie que les données sont correctement renvoyées
        assert result == {"elo": 1200, "region": "EU"}

@pytest.mark.asyncio
async def test_get_user_info_not_found():
    # Mock une réponse nulle de la base de données
    with patch("utils.database.database.fetchrow", new=AsyncMock(return_value=None)):
        # Appelle la fonction
        result = await MatchmakingService.get_user_info(123456789)
        
        # Vérifie que None est renvoyé
        assert result is None

@pytest.mark.asyncio
async def test_get_user_info_error():
    # Mock une exception levée par la base de données
    with patch("utils.database.database.fetchrow", new=AsyncMock(side_effect=Exception("Database error"))):
        # Appelle la fonction
        result = await MatchmakingService.get_user_info(123456789)
        
        # Vérifie que le résultat est None en cas d'erreur
        assert result is None
@pytest.mark.asyncio
async def test_get_server_id_found():
    # Mock la réponse de la base de données
    mock_server_id = 42
    with patch("utils.database.database.fetchval", new=AsyncMock(return_value=mock_server_id)):
        result = await MatchmakingService.get_server_id(123456789)
        assert result == 42  # Vérifie que l'ID correct est renvoyé

@pytest.mark.asyncio
async def test_get_server_id_not_found():
    # Mock une réponse nulle de la base de données
    with patch("utils.database.database.fetchval", new=AsyncMock(return_value=None)):
        result = await MatchmakingService.get_server_id(123456789)
        assert result is None  # Vérifie que None est renvoyé si le server_id n'est pas trouvé

@pytest.mark.asyncio
async def test_get_server_id_error():
    # Mock une exception levée par la base de données
    with patch("utils.database.database.fetchval", new=AsyncMock(side_effect=Exception("Database error"))):
        result = await MatchmakingService.get_server_id(123456789)
        assert result is None  # Vérifie que None est renvoyé en cas d'erreur

@pytest.mark.asyncio
async def test_get_role_id_found():
    # Mock la réponse de la base de données
    mock_role_id = 123456
    with patch("utils.database.database.fetchval", new=AsyncMock(return_value=mock_role_id)):
        result = await MatchmakingService.get_role_id(42, "admin")
        assert result == 123456  # Vérifie que l'ID du rôle est correct

@pytest.mark.asyncio
async def test_get_role_id_not_found():
    # Mock une réponse nulle de la base de données
    with patch("utils.database.database.fetchval", new=AsyncMock(return_value=None)):
        result = await MatchmakingService.get_role_id(42, "admin")
        assert result is None  # Vérifie que None est renvoyé si le rôle n'existe pas

@pytest.mark.asyncio
async def test_get_role_id_error():
    # Mock une exception levée par la base de données
    with patch("utils.database.database.fetchval", new=AsyncMock(side_effect=Exception("Database error"))):
        result = await MatchmakingService.get_role_id(42, "admin")
        assert result is None  # Vérifie que None est renvoyé en cas d'erreur

@pytest.mark.asyncio
async def test_get_language_roles_all_found():
    # Mock les réponses pour tous les rôles
    role_ids = {"francais": 1, "anglais": 2, "espagnol": 3}
    async def mock_get_role_id(server_id, role_name):
        return role_ids.get(role_name, None)
    
    with patch("cogs.voice_management.services.five_stack_service.MatchmakingService.get_role_id", new=AsyncMock(side_effect=mock_get_role_id)):
        result = await MatchmakingService.get_language_roles(42)
        assert result == role_ids  # Vérifie que tous les rôles sont correctement récupérés

@pytest.mark.asyncio
async def test_get_language_roles_partial_found():
    # Mock les réponses pour certains rôles
    role_ids = {"francais": 1, "anglais": None, "espagnol": 3}
    async def mock_get_role_id(server_id, role_name):
        return role_ids.get(role_name, None)
    
    with patch("cogs.voice_management.services.five_stack_service.MatchmakingService.get_role_id", new=AsyncMock(side_effect=mock_get_role_id)):
        result = await MatchmakingService.get_language_roles(42)
        assert result == {"francais": 1, "espagnol": 3}  # Vérifie que seuls les rôles trouvés sont renvoyés

@pytest.mark.asyncio
async def test_get_language_roles_none_found():
    # Mock aucune réponse
    async def mock_get_role_id(server_id, role_name):
        return None
    
    with patch("cogs.voice_management.services.five_stack_service.MatchmakingService.get_role_id", new=AsyncMock(side_effect=mock_get_role_id)):
        result = await MatchmakingService.get_language_roles(42)
        assert result == {}  # Vérifie que le dictionnaire est vide si aucun rôle n'est trouvé

@pytest.mark.asyncio
async def test_get_language_roles_error():
    # Mock une exception levée pour un rôle spécifique
    async def mock_get_role_id(server_id, role_name):
        if role_name == "anglais":
            raise Exception("Database error")
        return 1
    
    with patch("cogs.voice_management.services.five_stack_service.MatchmakingService.get_role_id", new=AsyncMock(side_effect=mock_get_role_id)):
        result = await MatchmakingService.get_language_roles(42)
        # Vérifie que les rôles valides sont toujours renvoyés malgré l'erreur
        assert result == {"francais": 1, "espagnol": 1}

@pytest.mark.asyncio
async def test_save_persistent_message_success():
    # Mock une exécution réussie de la requête
    with patch("utils.database.database.execute", new=AsyncMock(return_value=None)) as mock_execute:
        await MatchmakingService.save_persistent_message(42, "queue_status", 123, 456)

        # Vérifie que la requête a été appelée avec les bons arguments
        mock_execute.assert_called_once_with(
            """
            INSERT INTO persistent_messages (guild_id, message_type, channel_id, message_id)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, message_type)
            DO UPDATE SET channel_id = EXCLUDED.channel_id, message_id = EXCLUDED.message_id;
            """,
            42, "queue_status", 123, 456
        )

@pytest.mark.asyncio
async def test_save_persistent_message_error():
    # Mock une exception levée par la base de données
    with patch("utils.database.database.execute", new=AsyncMock(side_effect=Exception("Database error"))):
        await MatchmakingService.save_persistent_message(42, "queue_status", 123, 456)

        # Une erreur doit être loguée mais aucune exception ne doit être levée
        # Vous pouvez vérifier le log ici si nécessaire
