"""Per-run logging: every loop run writes a timestamped file under logs/ and
echoes to stdout (so cron mail / console both capture it)."""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from config import settings


def setup_logging(loop_name: str, dry_run: bool = False) -> tuple[logging.Logger, Path]:
    settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_dryrun" if dry_run else ""
    log_path = settings.LOGS_DIR / f"{loop_name}_{ts}{suffix}.log"

    logger = logging.getLogger(f"loop.{loop_name}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%Y-%m-%d %H:%M:%S")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger, log_path
