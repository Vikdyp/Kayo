# logging_config.py
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Mapping


def setup_logging(
    log_levels: Mapping[str, int],
    log_dir: str = "logs",
    root_level: int = logging.WARNING,
) -> None:
    """
    Configure le logging global (console + fichier) et applique des niveaux
    spécifiques par logger.

    - root_level contrôle le niveau global (par défaut INFO)
    - log_levels permet d'overrider certains loggers (ex: "discord": WARNING)
    """

    Path(log_dir).mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(root_level)

    # Important: éviter l'empilement des handlers si setup_logging est rappelée
    root.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)  # Laisser passer tout, le filtrage est fait par les loggers
    console.setFormatter(fmt)

    file_handler = RotatingFileHandler(
        Path(log_dir) / "bot.log",
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)  # Laisser passer tout, le filtrage est fait par les loggers
    file_handler.setFormatter(fmt)

    root.addHandler(console)
    root.addHandler(file_handler)

    # Applique des niveaux spécifiques.
    # Note: les loggers sont hiérarchiques ("cogs" -> "cogs.admin" -> ...)
    for name, level in log_levels.items():
        logging.getLogger(name).setLevel(level)
