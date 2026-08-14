# CyberLab Agent v4.0
# core/logger.py

import logging
import os
from lab_v4.core.config import LOG_FILES

def setup_logger(name: str = "cyberlab") -> logging.Logger:
    os.makedirs("lab_v4/logs", exist_ok=True)

    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # DEBUG
    dh = logging.FileHandler(LOG_FILES["debug"])
    dh.setLevel(logging.DEBUG)
    dh.setFormatter(fmt)

    # INFO + WARNING
    ah = logging.FileHandler(LOG_FILES["agent"])
    ah.setLevel(logging.INFO)
    ah.setFormatter(fmt)

    # ERROR + CRITICAL
    eh = logging.FileHandler(LOG_FILES["errors"])
    eh.setLevel(logging.ERROR)
    eh.setFormatter(fmt)

    # Console
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(dh)
    logger.addHandler(ah)
    logger.addHandler(eh)
    logger.addHandler(ch)

    return logger

log = setup_logger()
