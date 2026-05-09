from __future__ import annotations

from cogs.fun.services import QuoiResponderService


def test_quoi_responder_matches_messages_ending_with_quoi() -> None:
    service = QuoiResponderService()

    assert service.matches_trigger("quoi")
    assert service.matches_trigger("Mais quoi ??")
    assert service.matches_trigger("QUOI!")
    assert not service.matches_trigger("pourquoi")
    assert not service.matches_trigger("quoi tu fais")


def test_quoi_responder_rate_limits_per_user() -> None:
    service = QuoiResponderService(max_responses_per_user=2, time_window_seconds=10)

    assert service.allow_response(42, now=100)
    assert service.allow_response(42, now=101)
    assert not service.allow_response(42, now=102)
    assert service.allow_response(42, now=111)


def test_quoi_responder_builds_response_with_emoji_suffix() -> None:
    service = QuoiResponderService(responses=("feur !",))

    assert service.build_response("<:pepe_clown:1>") == "feur ! <:pepe_clown:1>"
