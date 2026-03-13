"""Framework constants."""

from pathlib import Path

# Project root directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Storage directory for persistent data
STORAGE_DIR = BASE_DIR / "storage"

# Logs directory
LOGS_DIR = BASE_DIR / "logs"
