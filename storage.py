from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from typing import Any

from config import DATA_DIR, STATE_PATH

DEFAULT_SETTINGS: dict[str, Any] = {
    "timezone": "America/New_York",
    "schedule_days": "M",
    "schedule_time": "1200",
    "opentasks_schedule_days": "MTWHFSU",
    "opentasks_schedule_time": "1100",
    "purge_age_days": 30,
    "enabled_channel_ids": [],
    "last_announce_date": None,
    "last_opentasks_date": None,
}


def _empty_guild() -> dict[str, Any]:
    return {
        "settings": deepcopy(DEFAULT_SETTINGS),
        "tasks": [],
        "recent_purged": [],
        "daily_completion_msgs": {},
        "public_list_msgs": {},
    }


def _empty_state() -> dict[str, Any]:
    return {"guilds": {}}


def load_state() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        state = _empty_state()
        save_state(state)
        return state
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "guilds" not in data:
        data = {"guilds": {}}
    return data


def save_state(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=DATA_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, STATE_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get_guild(state: dict[str, Any], guild_id: int) -> dict[str, Any]:
    key = str(guild_id)
    guilds = state.setdefault("guilds", {})
    if key not in guilds:
        guilds[key] = _empty_guild()
    else:
        g = guilds[key]
        g.setdefault("settings", deepcopy(DEFAULT_SETTINGS))
        for k, v in DEFAULT_SETTINGS.items():
            g["settings"].setdefault(k, deepcopy(v) if not isinstance(v, (str, int, type(None))) else v)
        g.setdefault("tasks", [])
        g.setdefault("recent_purged", [])
        g.setdefault("daily_completion_msgs", {})
        g.setdefault("public_list_msgs", {})
    return guilds[key]
