from __future__ import annotations

from dataclasses import dataclass

from cogs.accueil.services import AccueilService
from cogs.configuration.services.channel_service import (
    ChannelConfigurationService as ChannelConfigurationWorkflowService,
)
from cogs.configuration.services.role_service import (
    RoleConfigurationService as RoleConfigurationWorkflowService,
)
from cogs.moderation.services.automod_service import AutomodService
from cogs.moderation.services.clean_service import CleanService
from cogs.moderation.services.moderation_service import ModerationService
from cogs.role_management.services import RoleSelectionService
from cogs.rules.services import RulesService
from cogs.voice_chat.services import TempVoiceService
from cogs.ranking.services.mmr_tracker_service import MmrTrackerService
from cogs.ranking.services.ranking_service import RankingService
from database.engine import Db
from database.services.automod_config_service import AutomodConfigService
from database.services.guild_channels_service import ChannelConfigurationService as ChannelConfigurationDbService
from database.services.guild_members_service import GuildMembersService
from database.services.guild_roles_service import RoleConfigurationService as RoleConfigurationDbService
from database.services.member_stats_service import MemberStatsService
from database.services.message_deletions_service import MessageDeletionsService
from database.services.moderation_service import ModerationDbService
from database.services.persistent_messages_service import PersistentMessagesService
from database.services.unban_requests_service import UnbanRequestsService
from database.services.valorant_db_service import ValorantDbService
from integrations.henrikdev.service import HenrikDevService
from integrations.http_client import HTTPClient


@dataclass(slots=True)
class ServiceContainer:
    http_client: HTTPClient
    channel_configuration_service: ChannelConfigurationWorkflowService
    role_configuration_service: RoleConfigurationWorkflowService
    accueil_service: AccueilService
    clean_service: CleanService
    automod_service: AutomodService
    moderation_service: ModerationService
    unban_requests_service: UnbanRequestsService
    rules_service: RulesService
    role_selection_service: RoleSelectionService
    temp_voice_service: TempVoiceService
    ranking_service: RankingService
    henrik_service: HenrikDevService
    mmr_tracker_service: MmrTrackerService


async def build_service_container(db: Db, henrik_api_key: str) -> ServiceContainer:
    member_stats_db_service = MemberStatsService(db)
    persistent_messages_db_service = PersistentMessagesService(db)
    channel_config_db_service = ChannelConfigurationDbService(db)
    role_config_db_service = RoleConfigurationDbService(db)
    guild_members_db_service = GuildMembersService(db)
    message_deletions_db_service = MessageDeletionsService(db)
    automod_config_db_service = AutomodConfigService(db)
    moderation_db_service = ModerationDbService(db)
    unban_requests_db_service = UnbanRequestsService(db)
    valorant_db_service = ValorantDbService(db)
    channel_configuration_service = ChannelConfigurationWorkflowService(channel_config_db_service)
    role_configuration_service = RoleConfigurationWorkflowService(role_config_db_service)

    http_client = HTTPClient(timeout_seconds=15.0)
    await http_client.__aenter__()
    henrik_service = HenrikDevService(http_client, henrik_api_key)

    accueil_service = AccueilService(
        member_stats_db_service,
        persistent_messages_db_service,
        channel_config_db_service,
    )
    clean_service = CleanService(message_deletions_db_service)
    automod_service = AutomodService(automod_config_db_service)
    moderation_service = ModerationService(
        moderation_db_service,
        persistent_messages_db_service,
        role_config_db_service,
        channel_config_db_service,
    )
    rules_service = RulesService(
        channel_config_db_service,
        guild_members_db_service,
        persistent_messages_db_service,
    )
    role_selection_service = RoleSelectionService(
        role_config_db_service,
        persistent_messages_db_service,
    )
    temp_voice_service = TempVoiceService(channel_config_db_service)
    ranking_service = RankingService(
        valorant_db_service,
        channel_config_db_service,
        role_config_db_service,
        persistent_messages_db_service,
    )
    mmr_tracker_service = MmrTrackerService(valorant_db_service, henrik_service)

    return ServiceContainer(
        http_client=http_client,
        channel_configuration_service=channel_configuration_service,
        role_configuration_service=role_configuration_service,
        accueil_service=accueil_service,
        clean_service=clean_service,
        automod_service=automod_service,
        moderation_service=moderation_service,
        unban_requests_service=unban_requests_db_service,
        rules_service=rules_service,
        role_selection_service=role_selection_service,
        temp_voice_service=temp_voice_service,
        ranking_service=ranking_service,
        henrik_service=henrik_service,
        mmr_tracker_service=mmr_tracker_service,
    )
