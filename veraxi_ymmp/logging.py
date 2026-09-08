"""
Structured logging setup for veraxi-ymmp.
"""

import logging
import sys
from typing import Optional


logger = logging.getLogger(__name__)


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    console: bool = True
) -> None:
    """
    Setup logging configuration for the application.
    """
    # Create the root logger if not configuring root, but let's configure veraxi_ymmp specifically
    app_logger = logging.getLogger("veraxi_ymmp")
    app_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates if called multiple times
    app_logger.handlers.clear()

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    if console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(level)
        ch.setFormatter(formatter)
        app_logger.addHandler(ch)

    if log_file:
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setLevel(level)
        fh.setFormatter(formatter)
        app_logger.addHandler(fh)
