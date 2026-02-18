import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # Load .env before reading environment variables

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = BASE_DIR / "logs"

DEFAULT_MODEL = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
