"""
Runtime configuration — read from environment variables or .env file.

Copy .env.example to .env and fill in your API keys:
    cp .env.example .env
"""
import os
from pathlib import Path

# Load .env if present (no python-dotenv dependency — stdlib only)
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# API keys — set in .env or your shell environment
API_FOOTBALL_KEY: str = os.getenv("API_FOOTBALL_KEY", "")
ODDS_API_KEY: str     = os.getenv("ODDS_API_KEY", "")

# SQLite database path
DB_PATH: str = os.getenv(
    "DB_PATH",
    str(Path(__file__).parent / "data" / "tippekupongen.db"),
)
