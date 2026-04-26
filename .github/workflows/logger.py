# =============================================================================
# logger.py -- Centralised logging for AutonomusAI
# Writes to both console and bot.log with timestamps.
# =============================================================================

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_FILE    = os.path.join(os.path.dirname(__file__), "bot.log")
LOG_FORMAT  = "%(asctime)s | %(levelname)-8s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str = "AutonomusAI") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.DEBUG)

    # Rotating file handler -- max 5MB per file, keep 5 backups
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


log = get_logger()
