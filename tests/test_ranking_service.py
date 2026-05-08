from __future__ import annotations

from cogs.ranking.services.ranking_service import RankingService


class FakeValorantDb:
    pass


class FakePersistentMessages:
    def __init__(self):
        self.saved: list[tuple[object, ...]] = []

    async def save(self, *args):
        self.saved.append(args)

    async def get(self, guild_id: int, message_type: str):
        return None


def make_service() -> RankingService:
    fake = FakePersistentMessages()
    return RankingService(FakeValorantDb(), fake, fake, fake)


def test_get_role_key_for_rank_uses_rank_tiers_case_insensitively():
    service = make_service()

    assert service.get_role_key_for_rank("Gold 2") == "or"
    assert service.get_role_key_for_rank("IMMORTAL 1") == "immortel"


def test_get_role_key_for_rank_returns_none_for_unknown_rank():
    service = make_service()

    assert service.get_role_key_for_rank("Unrated") == "no_rank"
    assert service.get_role_key_for_rank(None) is None


async def test_store_persistent_message_uses_service_argument_order():
    persistent = FakePersistentMessages()
    fake = FakePersistentMessages()
    service = RankingService(FakeValorantDb(), fake, fake, persistent)

    result = await service.store_persistent_message(
        guild_id=1,
        guild_name="Guild",
        channel_id=2,
        message_id=3,
        msg_type="embed_rank",
    )

    assert result is True
    assert persistent.saved == [(1, "Guild", "embed_rank", 2, 3)]
