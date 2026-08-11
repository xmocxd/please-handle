from __future__ import annotations

import discord

import tasks_service as svc
from config import MAX_LAYOUT_COMPONENTS
from storage import get_guild, load_state

# Accent colors
COLOR_UNASSIGNED = discord.Color.from_str("#E67E22")
COLOR_ASSIGNED = discord.Color.from_str("#3498DB")
COLOR_COMPLETE = discord.Color.from_str("#27AE60")


def _count_items(view: discord.ui.LayoutView) -> int:
    """Rough nested component count for truncation."""

    def walk(items) -> int:
        total = 0
        for item in items:
            total += 1
            children = getattr(item, "children", None)
            if children is not None:
                total += walk(children)
        return total

    return walk(view.children)


def build_public_tasklist_view(guild_id: int) -> discord.ui.LayoutView:
    # Import here to avoid circular import at module load for type checkers;
    # runtime needs the button classes.
    from views import MarkDoneButton, PickupButton, PutdownButton

    state = load_state()
    guild = get_guild(state, guild_id)
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.TextDisplay("# Tasks"))

    budget = MAX_LAYOUT_COMPONENTS - 3  # footer + truncation note headroom
    truncated = False

    # --- Unassigned ---
    unassigned = svc.unassigned_tasks(guild)
    un_items: list[discord.ui.Item] = [discord.ui.TextDisplay("## Unassigned")]
    if not unassigned:
        un_items.append(discord.ui.TextDisplay("_None_"))
    else:
        for i, task in enumerate(unassigned, start=1):
            # TextDisplay + ActionRow + Button ~= 3 nested under container
            if len(un_items) + 2 > budget:
                un_items.append(discord.ui.TextDisplay(f"_…and {len(unassigned) - i + 1} more unassigned_"))
                truncated = True
                break
            un_items.append(discord.ui.TextDisplay(f"{i}. {task['description']}"))
            row = discord.ui.ActionRow()
            row.add_item(PickupButton(task["id"]))
            un_items.append(row)
    view.add_item(discord.ui.Container(*un_items, accent_colour=COLOR_UNASSIGNED))

    # --- Per assignee (order matches each user's numbered list) ---
    if not truncated:
        for user_id in svc.assignees_in_order(guild):
            if _count_items(view) >= budget:
                truncated = True
                break
            tasks = svc.user_tasks(guild, user_id)
            if not tasks:
                continue

            section_items: list[discord.ui.Item] = [
                discord.ui.TextDisplay(f"## <@{user_id}>'s Tasks")
            ]
            has_incomplete = False
            for n, task in enumerate(tasks, start=1):
                if task.get("completed"):
                    section_items.append(
                        discord.ui.TextDisplay(f"{n}. ~~{task['description']}~~ ✅")
                    )
                else:
                    has_incomplete = True
                    section_items.append(discord.ui.TextDisplay(f"{n}. {task['description']}"))
                    row = discord.ui.ActionRow()
                    row.add_item(PutdownButton(task["id"], source="pub"))
                    row.add_item(MarkDoneButton(task["id"], source="pub"))
                    section_items.append(row)

            accent = COLOR_ASSIGNED if has_incomplete else COLOR_COMPLETE
            view.add_item(discord.ui.Container(*section_items, accent_colour=accent))

            if _count_items(view) >= budget:
                truncated = True
                break

    if truncated:
        view.add_item(
            discord.ui.TextDisplay("_List truncated — use slash commands for the rest._")
        )

    view.add_item(discord.ui.Separator(visible=True))
    view.add_item(discord.ui.TextDisplay("Please Handle"))
    return view


def build_mytasks_view(guild_id: int, user_id: int) -> discord.ui.LayoutView:
    from views import MarkDoneButton, PutdownButton

    state = load_state()
    guild = get_guild(state, guild_id)
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.TextDisplay("## Your Tasks:"))

    tasks = svc.user_tasks(guild, user_id)
    if not tasks:
        view.add_item(discord.ui.TextDisplay("_No tasks assigned._"))
        return view

    for i, task in enumerate(tasks, start=1):
        if task.get("completed"):
            view.add_item(
                discord.ui.TextDisplay(f"{i}. ~~{task['description']}~~ ✅")
            )
        else:
            view.add_item(discord.ui.TextDisplay(f"{i}. {task['description']}"))
            row = discord.ui.ActionRow()
            row.add_item(PutdownButton(task["id"], source="priv"))
            row.add_item(MarkDoneButton(task["id"], source="priv"))
            view.add_item(row)
        if _count_items(view) >= MAX_LAYOUT_COMPONENTS:
            view.add_item(discord.ui.TextDisplay("_List truncated._"))
            break

    return view


def settings_text(guild_id: int) -> str:
    state = load_state()
    guild = get_guild(state, guild_id)
    s = guild["settings"]
    channels = s.get("enabled_channel_ids") or []
    ch_list = ", ".join(f"<#{c}>" for c in channels) if channels else "_none_"
    return (
        "**please-handle settings**\n"
        f"- Timezone: `{s.get('timezone')}`\n"
        f"- Schedule: `{s.get('schedule_days')} {s.get('schedule_time')}`\n"
        f"- Purge age: `{s.get('purge_age_days')}` days\n"
        f"- Enabled channels: {ch_list}\n"
        f"- Last announce date: `{s.get('last_announce_date')}`\n"
        f"- Active tasks: `{len(guild['tasks'])}`\n"
        f"- Recent purged buffer: `{len(guild.get('recent_purged') or [])}`"
    )
