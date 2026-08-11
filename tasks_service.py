from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import RECENT_PURGED_LIMIT
from storage import get_guild, load_state, save_state

DAY_LETTERS = "MTWHFSU"
# Mon=0 .. Sun=6
LETTER_TO_WEEKDAY = {"M": 0, "T": 1, "W": 2, "H": 3, "F": 4, "S": 5, "U": 6}
WEEKDAY_TO_LETTER = {v: k for k, v in LETTER_TO_WEEKDAY.items()}


class ServiceError(Exception):
    """User-facing domain error."""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def guild_now(guild: dict[str, Any]) -> datetime:
    tz_name = guild["settings"].get("timezone") or "America/New_York"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("America/New_York")
    return datetime.now(tz)


def unassigned_tasks(guild: dict[str, Any], *, include_completed: bool = False) -> list[dict[str, Any]]:
    out = []
    for t in guild["tasks"]:
        if t.get("assignee_id") is not None:
            continue
        if t.get("completed") and not include_completed:
            continue
        out.append(t)
    return out


def user_tasks(guild: dict[str, Any], user_id: int) -> list[dict[str, Any]]:
    return [t for t in guild["tasks"] if t.get("assignee_id") == user_id]


def assignees_in_order(guild: dict[str, Any]) -> list[int]:
    seen: list[int] = []
    for t in guild["tasks"]:
        aid = t.get("assignee_id")
        if aid is not None and aid not in seen:
            seen.append(aid)
    return seen


def get_task_by_id(guild: dict[str, Any], task_id: str) -> Optional[dict[str, Any]]:
    for t in guild["tasks"]:
        if t["id"] == task_id:
            return t
    return None


def task_by_unassigned_number(guild: dict[str, Any], number: int) -> dict[str, Any]:
    tasks = unassigned_tasks(guild)
    if number < 1 or number > len(tasks):
        raise ServiceError(f"No unassigned task #{number}.")
    return tasks[number - 1]


def task_by_user_number(guild: dict[str, Any], user_id: int, number: int) -> dict[str, Any]:
    tasks = user_tasks(guild, user_id)
    if number < 1 or number > len(tasks):
        raise ServiceError(f"No task #{number} on that user's list.")
    return tasks[number - 1]


def format_user_task_list(guild: dict[str, Any], user_id: int) -> str:
    tasks = user_tasks(guild, user_id)
    if not tasks:
        return "_No tasks._"
    lines = []
    for i, t in enumerate(tasks, start=1):
        if t.get("completed"):
            lines.append(f"{i}. ~~{t['description']}~~ ✅")
        else:
            lines.append(f"{i}. {t['description']}")
    return "\n".join(lines)


# --- mutations (load/save around each public op) ---

def new_task(guild_id: int, description: str) -> dict[str, Any]:
    description = description.strip()
    if not description:
        raise ServiceError("Task description cannot be empty.")
    state = load_state()
    guild = get_guild(state, guild_id)
    task = {
        "id": str(uuid.uuid4()),
        "description": description,
        "assignee_id": None,
        "completed": False,
        "completed_at": None,
        "created_at": _iso(_now_utc()),
    }
    guild["tasks"].append(task)
    save_state(state)
    return task


def pickup_task(guild_id: int, user_id: int, number: int) -> dict[str, Any]:
    state = load_state()
    guild = get_guild(state, guild_id)
    task = task_by_unassigned_number(guild, number)
    if task.get("completed"):
        raise ServiceError("That task is already completed.")
    task["assignee_id"] = user_id
    save_state(state)
    return task


def pickup_task_by_id(guild_id: int, user_id: int, task_id: str) -> dict[str, Any]:
    state = load_state()
    guild = get_guild(state, guild_id)
    task = get_task_by_id(guild, task_id)
    if task is None:
        raise ServiceError("Task not found.")
    if task.get("assignee_id") is not None:
        raise ServiceError("That task is already assigned.")
    if task.get("completed"):
        raise ServiceError("That task is already completed.")
    task["assignee_id"] = user_id
    save_state(state)
    return task


def drop_task(guild_id: int, user_id: int, number: int) -> dict[str, Any]:
    state = load_state()
    guild = get_guild(state, guild_id)
    task = task_by_user_number(guild, user_id, number)
    if task.get("completed"):
        raise ServiceError("Completed tasks cannot be dropped.")
    task["assignee_id"] = None
    save_state(state)
    return task


def drop_task_by_id(guild_id: int, user_id: int, task_id: str) -> dict[str, Any]:
    state = load_state()
    guild = get_guild(state, guild_id)
    task = get_task_by_id(guild, task_id)
    if task is None:
        raise ServiceError("Task not found.")
    if task.get("assignee_id") != user_id:
        raise ServiceError("That task is not assigned to you.")
    if task.get("completed"):
        raise ServiceError("Completed tasks cannot be dropped.")
    task["assignee_id"] = None
    save_state(state)
    return task


def mark_done(guild_id: int, user_id: int, number: int) -> dict[str, Any]:
    state = load_state()
    guild = get_guild(state, guild_id)
    task = task_by_user_number(guild, user_id, number)
    if task.get("completed"):
        raise ServiceError("That task is already completed.")
    task["completed"] = True
    task["completed_at"] = _iso(_now_utc())
    save_state(state)
    return task


def mark_done_by_id(guild_id: int, user_id: int, task_id: str) -> dict[str, Any]:
    state = load_state()
    guild = get_guild(state, guild_id)
    task = get_task_by_id(guild, task_id)
    if task is None:
        raise ServiceError("Task not found.")
    if task.get("assignee_id") != user_id:
        raise ServiceError("That task is not assigned to you.")
    if task.get("completed"):
        raise ServiceError("That task is already completed.")
    task["completed"] = True
    task["completed_at"] = _iso(_now_utc())
    save_state(state)
    return task


def assign_task(guild_id: int, number: int, target_user_id: int) -> dict[str, Any]:
    state = load_state()
    guild = get_guild(state, guild_id)
    task = task_by_unassigned_number(guild, number)
    if task.get("completed"):
        raise ServiceError("That task is already completed.")
    task["assignee_id"] = target_user_id
    save_state(state)
    return task


def unassign_task(guild_id: int, target_user_id: int, number: int) -> dict[str, Any]:
    state = load_state()
    guild = get_guild(state, guild_id)
    task = task_by_user_number(guild, target_user_id, number)
    if task.get("completed"):
        raise ServiceError("Completed tasks cannot be unassigned; wait for purge or leave them.")
    task["assignee_id"] = None
    save_state(state)
    return task


def remove_task(guild_id: int, number: int) -> dict[str, Any]:
    state = load_state()
    guild = get_guild(state, guild_id)
    task = task_by_unassigned_number(guild, number)
    guild["tasks"] = [t for t in guild["tasks"] if t["id"] != task["id"]]
    save_state(state)
    return task


def purge_completed(
    guild_id: int, *, age_days: Optional[int] = None, force: bool = False
) -> list[dict[str, Any]]:
    state = load_state()
    guild = get_guild(state, guild_id)
    settings = guild["settings"]
    days = age_days if age_days is not None else int(settings.get("purge_age_days", 30))
    cutoff = _now_utc() - timedelta(days=days)
    kept: list[dict[str, Any]] = []
    purged: list[dict[str, Any]] = []
    for t in guild["tasks"]:
        if not t.get("completed"):
            kept.append(t)
            continue
        completed_at = t.get("completed_at")
        if not force:
            if not completed_at:
                kept.append(t)
                continue
            if _parse_iso(completed_at) >= cutoff:
                kept.append(t)
                continue
        purged.append(
            {
                "id": t["id"],
                "description": t["description"],
                "assignee_id": t.get("assignee_id"),
                "completed_at": completed_at,
                "purged_at": _iso(_now_utc()),
            }
        )
    guild["tasks"] = kept
    if purged:
        recent = guild.setdefault("recent_purged", [])
        recent.extend(purged)
        guild["recent_purged"] = recent[-RECENT_PURGED_LIMIT:]
    save_state(state)
    return purged


def set_daily_completion_msg(
    guild_id: int, user_id: int, date_str: str, channel_id: int, message_id: int
) -> None:
    state = load_state()
    guild = get_guild(state, guild_id)
    key = f"{user_id}:{date_str}"
    guild["daily_completion_msgs"][key] = {
        "channel_id": channel_id,
        "message_id": message_id,
    }
    save_state(state)


def get_daily_completion_msg(guild_id: int, user_id: int, date_str: str) -> Optional[dict[str, int]]:
    state = load_state()
    guild = get_guild(state, guild_id)
    key = f"{user_id}:{date_str}"
    return guild.get("daily_completion_msgs", {}).get(key)


def record_public_list(
    guild_id: int,
    channel_id: int,
    *,
    unassigned_message_id: int,
    assignee_message_ids: dict[int, int],
) -> None:
    """Remember the latest public list messages posted in a channel."""
    state = load_state()
    guild = get_guild(state, guild_id)
    guild.setdefault("public_list_msgs", {})[str(channel_id)] = {
        "unassigned_message_id": unassigned_message_id,
        "assignees": {str(uid): mid for uid, mid in assignee_message_ids.items()},
    }
    save_state(state)


def get_public_list_msgs(guild_id: int) -> dict[str, Any]:
    state = load_state()
    guild = get_guild(state, guild_id)
    return dict(guild.get("public_list_msgs") or {})


def update_public_list_assignee_msg(
    guild_id: int, channel_id: int, user_id: int, message_id: int
) -> None:
    state = load_state()
    guild = get_guild(state, guild_id)
    channel = guild.setdefault("public_list_msgs", {}).setdefault(
        str(channel_id),
        {"unassigned_message_id": None, "assignees": {}},
    )
    channel.setdefault("assignees", {})[str(user_id)] = message_id
    save_state(state)


def enable_channel(guild_id: int, channel_id: int) -> bool:
    state = load_state()
    guild = get_guild(state, guild_id)
    ids = guild["settings"].setdefault("enabled_channel_ids", [])
    if channel_id in ids:
        return False
    ids.append(channel_id)
    save_state(state)
    return True


def disable_channel(guild_id: int, channel_id: int) -> bool:
    state = load_state()
    guild = get_guild(state, guild_id)
    ids = guild["settings"].setdefault("enabled_channel_ids", [])
    if channel_id not in ids:
        return False
    ids.remove(channel_id)
    save_state(state)
    return True


def parse_schedule(days: str, time_str: str) -> tuple[str, str]:
    days = days.strip().upper()
    time_str = time_str.strip()
    if not days or any(c not in DAY_LETTERS for c in days):
        raise ServiceError(f"Days must only use letters from {DAY_LETTERS} (e.g. MTWHFSU, MWF).")
    # preserve unique order of first occurrence
    seen = set()
    ordered = []
    for c in days:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    normalized_days = "".join(ordered)
    if not re.fullmatch(r"[0-2]\d[0-5]\d", time_str):
        raise ServiceError("Time must be 24-hour HHMM (e.g. 0900, 1700).")
    hour = int(time_str[:2])
    minute = int(time_str[2:])
    if hour > 23:
        raise ServiceError("Hour must be 00–23.")
    if minute > 59:
        raise ServiceError("Minute must be 00–59.")
    return normalized_days, time_str


def set_schedule(guild_id: int, days: str, time_str: str) -> tuple[str, str]:
    normalized_days, normalized_time = parse_schedule(days, time_str)
    state = load_state()
    guild = get_guild(state, guild_id)
    guild["settings"]["schedule_days"] = normalized_days
    guild["settings"]["schedule_time"] = normalized_time
    save_state(state)
    return normalized_days, normalized_time


def set_timezone(guild_id: int, tz_name: str) -> str:
    tz_name = tz_name.strip()
    try:
        ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as e:
        raise ServiceError(f"Unknown timezone: {tz_name}") from e
    state = load_state()
    guild = get_guild(state, guild_id)
    guild["settings"]["timezone"] = tz_name
    save_state(state)
    return tz_name


def set_purge_age(guild_id: int, age_days: int) -> int:
    if age_days < 1:
        raise ServiceError("Purge age must be at least 1 day.")
    state = load_state()
    guild = get_guild(state, guild_id)
    guild["settings"]["purge_age_days"] = age_days
    save_state(state)
    return age_days


def mark_announced(guild_id: int, date_str: str) -> None:
    state = load_state()
    guild = get_guild(state, guild_id)
    guild["settings"]["last_announce_date"] = date_str
    save_state(state)


def should_announce(guild: dict[str, Any]) -> bool:
    settings = guild["settings"]
    if not settings.get("enabled_channel_ids"):
        return False
    now = guild_now(guild)
    letter = WEEKDAY_TO_LETTER[now.weekday()]
    days = settings.get("schedule_days") or "M"
    time_str = settings.get("schedule_time") or "1200"
    if letter not in days:
        return False
    hhmm = f"{now.hour:02d}{now.minute:02d}"
    if hhmm != time_str:
        return False
    today = now.date().isoformat()
    if settings.get("last_announce_date") == today:
        return False
    return True


def is_privileged(user_id: int, guild_owner_id: Optional[int], privileged: set[int]) -> bool:
    if user_id in privileged:
        return True
    if guild_owner_id is not None and user_id == guild_owner_id:
        return True
    return False
