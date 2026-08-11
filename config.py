from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
STATE_PATH = DATA_DIR / "state.json"

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()

_raw_priv = os.getenv("PRIVILEGED_USERS", "")
PRIVILEGED_USERS: set[int] = set()
for part in _raw_priv.split(","):
    part = part.strip()
    if part:
        PRIVILEGED_USERS.add(int(part))

RECENT_PURGED_LIMIT = 50
MAX_LAYOUT_COMPONENTS = 40  # Discord LayoutView hard limit
