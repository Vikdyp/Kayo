from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "vps" / "kayo_bot_healthcheck.py"
SPEC = importlib.util.spec_from_file_location("kayo_bot_healthcheck", MODULE_PATH)
assert SPEC is not None
healthcheck = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = healthcheck
SPEC.loader.exec_module(healthcheck)


def _inspect_payload(*, running: bool = True, started_at: str = "2026-05-18T10:00:00Z") -> list[dict[str, object]]:
    return [
        {
            "Id": "abcdef1234567890",
            "Image": "image1234567890",
            "RestartCount": 2,
            "State": {
                "Running": running,
                "Status": "running" if running else "exited",
                "StartedAt": started_at,
                "FinishedAt": "2026-05-18T10:05:00Z",
                "ExitCode": 1 if not running else 0,
            },
        }
    ]


def test_parse_docker_inspect_running_container_is_ok() -> None:
    snapshot = healthcheck.parse_docker_inspect("kayo-bot", _inspect_payload())

    assert snapshot.exists is True
    assert snapshot.running is True
    assert snapshot.container_id == "abcdef123456"
    assert snapshot.restart_count == 2
    assert snapshot.status_key() == "ok"


def test_first_successful_check_does_not_notify() -> None:
    snapshot = healthcheck.parse_docker_inspect("kayo-bot", _inspect_payload())

    decision = healthcheck.decide_alert(snapshot, {})

    assert decision.should_notify is False
    assert decision.level == "ok"


def test_missing_container_notifies() -> None:
    snapshot = healthcheck.ContainerSnapshot(
        name="kayo-bot",
        exists=False,
        inspect_error="No such object: kayo-bot",
    )

    decision = healthcheck.decide_alert(snapshot, {})

    assert decision.should_notify is True
    assert decision.level == "critical"
    assert "absent" in decision.detail


def test_recovery_from_error_notifies() -> None:
    snapshot = healthcheck.parse_docker_inspect("kayo-bot", _inspect_payload())

    decision = healthcheck.decide_alert(snapshot, {"status_key": "not_running:exited:1"})

    assert decision.should_notify is True
    assert decision.title == "Kayo bot revenu OK"


def test_started_at_change_notifies_restart() -> None:
    snapshot = healthcheck.parse_docker_inspect(
        "kayo-bot",
        _inspect_payload(started_at="2026-05-18T11:00:00Z"),
    )

    decision = healthcheck.decide_alert(
        snapshot,
        {
            "status_key": "ok",
            "started_at": "2026-05-18T10:00:00Z",
            "restart_count": "2",
        },
    )

    assert decision.should_notify is True
    assert decision.level == "warning"
    assert "redemarre" in decision.title
