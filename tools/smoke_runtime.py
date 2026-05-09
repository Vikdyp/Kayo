from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot import COG_PATHS, KayoBot, _build_postgres_dsn
from core.bootstrap import build_service_container
from database.engine import Db, DbConfig
from database.migrate import run_migrations


async def run_smoke(*, apply_migrations: bool = True) -> dict[str, object]:
    db = Db(DbConfig(dsn=_build_postgres_dsn()))
    await db.open()

    bot = KayoBot()
    try:
        if apply_migrations:
            await run_migrations(db)

        services = await build_service_container(db, os.getenv("HENRIK_VALO_KEY", ""))

        bot.db = db
        bot.services = services
        bot._http_client = services.http_client
        bot.channel_configuration_service = services.channel_configuration_service
        bot.role_configuration_service = services.role_configuration_service
        bot.accueil_service = services.accueil_service
        bot.clean_service = services.clean_service
        bot.automod_service = services.automod_service
        bot.moderation_service = services.moderation_service
        bot.unban_requests_svc = services.unban_requests_service
        bot.file_counter_service = services.file_counter_service
        bot.reputation_service = services.reputation_service
        bot.rules_service = services.rules_service
        bot.role_selection_service = services.role_selection_service
        bot.twitch_notification_service = services.twitch_notification_service
        bot.twitch_api_service = services.twitch_api_service
        bot.temp_voice_service = services.temp_voice_service
        bot.ranking_service = services.ranking_service
        bot.rank_notification_service = services.rank_notification_service
        bot.henrik_service = services.henrik_service
        bot.mmr_tracker_service = services.mmr_tracker_service

        await bot._load_extensions(COG_PATHS)
        loaded_extensions = sorted(bot.extensions)

        return {
            "db_open": True,
            "migrations": "applied" if apply_migrations else "skipped",
            "service_container": "ok",
            "loaded_cogs": len(loaded_extensions),
            "extensions": loaded_extensions,
            "closed": False,
        }
    finally:
        for path in reversed(list(bot.extensions)):
            await bot.unload_extension(path)
        await bot.close()
        await db.close()


async def _amain() -> int:
    parser = argparse.ArgumentParser(description="Smoke test Kayo runtime without connecting to Discord gateway.")
    parser.add_argument(
        "--skip-migrations",
        action="store_true",
        help="Open DB and load runtime without applying pending migrations.",
    )
    args = parser.parse_args()

    result = await run_smoke(apply_migrations=not args.skip_migrations)
    result["closed"] = True
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
