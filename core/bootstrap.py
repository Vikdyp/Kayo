from __future__ import annotations

from dataclasses import dataclass

from cogs.accueil.services import AccueilService
from cogs.configuration.services.channel_service import (
    ChannelConfigurationService as ChannelConfigurationBusinessService,
)
from cogs.configuration.services.role_service import (
    RoleConfigurationService as RoleConfigurationBusinessService,
)
from cogs.moderation.services.automod_service import AutomodService
from cogs.moderation.services.clean_service import CleanService
from cogs.moderation.services.moderation_service import ModerationService
from cogs.ranking.services.mmr_tracker_service import MmrTrackerService
from cogs.ranking.services.ranking_service import RankingService
from database.engine import Db
from database.services.automod_config_service import AutomodConfigService
from database.services.guild_channels_service import ChannelConfigurationService
from database.services.guild_roles_service import RoleConfigurationService
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
    channel_configuration_service: ChannelConfigurationBusinessService
    role_configuration_service: RoleConfigurationBusinessService
    accueil_service: AccueilService
    clean_service: CleanService
    automod_service: AutomodService
    moderation_service: ModerationService
    unban_requests_service: UnbanRequestsService
    ranking_service: RankingService
    henrik_service: HenrikDevService
    mmr_tracker_service: MmrTrackerService


async def build_service_container(db: Db, henrik_api_key: str) -> ServiceContainer:
    member_stats_svc = MemberStatsService(db)
    persistent_msg_svc = PersistentMessagesService(db)
    channel_config_svc = ChannelConfigurationService(db)
    role_config_svc = RoleConfigurationService(db)
    message_deletions_svc = MessageDeletionsService(db)
    automod_config_svc = AutomodConfigService(db)
    moderation_db_svc = ModerationDbService(db)
    unban_requests_svc = UnbanRequestsService(db)
    valorant_db_svc = ValorantDbService(db)
    channel_configuration_service = ChannelConfigurationBusinessService(db)
    role_configuration_service = RoleConfigurationBusinessService(db)

    http_client = HTTPClient(timeout_seconds=15.0)
    await http_client.__aenter__()
    henrik_service = HenrikDevService(http_client, henrik_api_key)

    accueil_service = AccueilService(
        member_stats_svc,
        persistent_msg_svc,
        channel_config_svc,
    )
    clean_service = CleanService(message_deletions_svc)
    automod_service = AutomodService(automod_config_svc)
    moderation_service = ModerationService(
        moderation_db_svc,
        persistent_msg_svc,
        role_config_svc,
        channel_config_svc,
    )
    ranking_service = RankingService(
        valorant_db_svc,
        channel_config_svc,
        role_config_svc,
        persistent_msg_svc,
    )
    mmr_tracker_service = MmrTrackerService(valorant_db_svc, henrik_service)

    return ServiceContainer(
        http_client=http_client,
        channel_configuration_service=channel_configuration_service,
        role_configuration_service=role_configuration_service,
        accueil_service=accueil_service,
        clean_service=clean_service,
        automod_service=automod_service,
        moderation_service=moderation_service,
        unban_requests_service=unban_requests_svc,
        ranking_service=ranking_service,
        henrik_service=henrik_service,
        mmr_tracker_service=mmr_tracker_service,
    )
