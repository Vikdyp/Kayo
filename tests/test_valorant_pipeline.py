# tests/test_valorant_pipeline.py
"""
Test du pipeline Valorant avec un compte réel.
Usage: python -m pytest tests/test_valorant_pipeline.py -v -s
"""

import asyncio
import os
import sys

# Ajouter le répertoire racine au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from dotenv import load_dotenv

from integrations.http_client import HTTPClient
from integrations.henrikdev.service import HenrikDevService
from cogs.ranking.services.valorant_pipeline import (
    ValorantPipeline,
    UserPipelineState,
    PipelineStep,
)

load_dotenv()


@pytest.fixture
async def pipeline():
    """Crée un pipeline avec un client HTTP réel."""
    api_key = os.getenv("HENRIK_VALO_KEY")
    if not api_key:
        pytest.skip("HENRIK_VALO_KEY non défini dans l'environnement")

    http_client = HTTPClient(timeout_seconds=15.0)
    await http_client.__aenter__()

    service = HenrikDevService(http_client, api_key)
    pipeline = ValorantPipeline(service)

    yield pipeline

    await http_client.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_full_pipeline_curs4d(pipeline):
    """
    Test complet du pipeline pour le compte Curs4d#2908.

    Étapes testées:
    1. Account Resolution: name/tag -> puuid + region
    2. Platform Detection: puuid -> platform (pc/console)
    3. Rank Retrieval: puuid + region + platform -> rank + elo
    """
    # État initial: seulement name + tag
    state = UserPipelineState(
        discord_id=812367371570118756,  # Fake discord ID pour le test
        pseudo="Curs4d",
        tag="2908",
        puuid=None,
        region=None,
        platform=None,
        rank=None,
        elo=None,
        error_count=0,
        last_error_at=None,
    )

    print("\n" + "=" * 60)
    print("TEST PIPELINE VALORANT - Curs4d#2908")
    print("=" * 60)

    # --- ÉTAPE 1: Account Resolution ---
    print("\n[ÉTAPE 1] Account Resolution...")
    assert state.current_step == PipelineStep.ACCOUNT_RESOLUTION

    result, rate_limit = await pipeline.execute_step(state)

    print(f"  Success: {result.success}")
    print(f"  PUUID: {result.puuid}")
    print(f"  Region: {result.region}")
    if rate_limit:
        print(f"  Rate Limit: {rate_limit.remaining}/{rate_limit.limit}")

    assert result.success, f"Account Resolution failed: {result.error_message}"
    assert result.puuid is not None
    assert result.region is not None

    # Mettre à jour l'état
    state.puuid = result.puuid
    state.region = result.region

    # --- ÉTAPE 2: Platform Detection ---
    print("\n[ÉTAPE 2] Platform Detection...")
    assert state.current_step == PipelineStep.PLATFORM_DETECTION

    result, rate_limit = await pipeline.execute_step(state)

    print(f"  Success: {result.success}")
    print(f"  Platform: {result.platform}")
    if rate_limit:
        print(f"  Rate Limit: {rate_limit.remaining}/{rate_limit.limit}")

    if not result.success:
        print(f"  Note: Platform detection failed (no matches yet): {result.error_message}")
        print("  Le joueur n'a peut-être pas encore joué de parties.")
        return  # On arrête le test ici si pas de platform détectée

    assert result.platform in ("pc", "console")
    state.platform = result.platform

    # --- ÉTAPE 3: Rank Retrieval ---
    print("\n[ÉTAPE 3] Rank Retrieval...")
    assert state.current_step == PipelineStep.RANK_RETRIEVAL

    result, rate_limit = await pipeline.execute_step(state)

    print(f"  Success: {result.success}")
    print(f"  Rank: {result.rank}")
    print(f"  Elo: {result.elo}")
    if rate_limit:
        print(f"  Rate Limit: {rate_limit.remaining}/{rate_limit.limit}")

    if not result.success:
        print(f"  Note: Rank retrieval failed: {result.error_message}")
        print("  Le joueur n'a peut-être pas encore de rang cette saison.")
        return

    assert result.rank is not None
    assert result.elo is not None

    print("\n" + "=" * 60)
    print("RÉSUMÉ FINAL")
    print("=" * 60)
    print(f"  Compte: Curs4d#2908")
    print(f"  PUUID: {state.puuid[:8]}...")
    print(f"  Region: {state.region}")
    print(f"  Platform: {state.platform}")
    print(f"  Rank: {result.rank}")
    print(f"  Elo: {result.elo}")
    print("=" * 60)


async def run_standalone_test():
    """Version standalone du test (sans pytest)."""
    api_key = os.getenv("HENRIK_VALO_KEY")
    if not api_key:
        print("ERREUR: HENRIK_VALO_KEY non défini dans l'environnement")
        return

    http_client = HTTPClient(timeout_seconds=15.0)
    await http_client.__aenter__()

    try:
        service = HenrikDevService(http_client, api_key)
        pipeline_instance = ValorantPipeline(service)
        await test_full_pipeline_curs4d(pipeline_instance)
    finally:
        await http_client.__aexit__(None, None, None)


if __name__ == "__main__":
    # Permet de lancer le test directement avec: python tests/test_valorant_pipeline.py
    asyncio.run(run_standalone_test())
