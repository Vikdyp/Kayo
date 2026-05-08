from __future__ import annotations

import re
from pathlib import Path

import bot


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _python_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".py":
            files.append(path)
        elif path.is_dir():
            files.extend(path.rglob("*.py"))
    return files


def _active_cog_roots() -> list[Path]:
    roots = set()
    for module_name in bot.COG_PATHS:
        parts = module_name.split(".")
        assert parts[:1] == ["cogs"]
        assert parts[1] != "_legacy"
        roots.add(PROJECT_ROOT / "cogs" / parts[1])
    return sorted(roots)


def _active_business_service_files() -> list[Path]:
    return [
        path
        for path in _python_files(_active_cog_roots())
        if "services" in path.relative_to(PROJECT_ROOT).parts
    ]


def test_active_cogs_do_not_reference_legacy_package():
    assert all(not path.startswith("cogs._legacy.") for path in bot.COG_PATHS)


def test_active_runtime_does_not_import_legacy_database_helper():
    files = _python_files(_active_cog_roots() + [PROJECT_ROOT / "core"])
    offenders = [
        str(path.relative_to(PROJECT_ROOT))
        for path in files
        if "utils.database" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_active_runtime_does_not_call_real_discord_ban():
    ban_call = re.compile(r"\.ban\s*\(")
    files = _python_files(_active_cog_roots() + [PROJECT_ROOT / "core"])
    offenders = [
        str(path.relative_to(PROJECT_ROOT))
        for path in files
        if ban_call.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_active_business_services_do_not_import_repos_or_asyncpg():
    forbidden_import = re.compile(
        r"^\s*(from\s+(database\.repos|asyncpg)\b|import\s+(database\.repos|asyncpg)\b)",
        re.MULTILINE,
    )
    offenders = [
        str(path.relative_to(PROJECT_ROOT))
        for path in _active_business_service_files()
        if forbidden_import.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_integrations_package_contains_no_manual_test_scripts():
    integrations_dir = PROJECT_ROOT / "integrations"
    offenders = sorted(
        {
            str(path.relative_to(PROJECT_ROOT))
            for pattern in ("test*.py", "*_test.py")
            for path in integrations_dir.glob(pattern)
        }
    )

    assert offenders == []
