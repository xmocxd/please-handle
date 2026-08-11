from __future__ import annotations

import discord

import tasks_service as svc
from config import MAX_LAYOUT_COMPONENTS
from storage import get_guild, load_state

# Accent colors
COLOR_UNASSIGNED = discord.Color.from_str("#E67E22")
COLOR_ASSIGNED = discord.Color.from_str("#3498DB")
COLOR_COMPLETE = discord.Color.from_str("#27AE60")

_BUTTON_LABEL_MAX = 80


def _count_items(view: discord.ui.LayoutView) -> int:
    """Rough nested component count for truncation."""

    def walk(items) -> int:
        total = 0
        for item in items:
            total += 1
            children = getattr(item, "children", None)
            if children is not None:
                total += walk(children)
            accessory = getattr(item, "accessory", None)
            if accessory is not None:
                total += 1
                acc_children = getattr(accessory, "children", None)
                if acc_children is not None:
                    total += walk(acc_children)
        return total

    return walk(view.children)


def _truncate_label(text: str) -> str:
    if len(text) <= _BUTTON_LABEL_MAX:
        return text
    return text[: _BUTTON_LABEL_MAX - 1] + "…"


def _task_section(text: str, *buttons: discord.ui.Item) -> discord.ui.Item:
    """Task text with action button(s) on the same line to the right."""
    if len(buttons) == 1:
        # Components V2 Section: text left, one button right
        return discord.ui.Section(text, accessory=buttons[0])
    # Discord only allows a single Button/Thumbnail accessory on a Section.
    # Keep label + actions on one ActionRow so they stay on the same line.
    row = discord.ui.ActionRow()
    row.add_item(
        discord.ui.Button(
            label=_truncate_label(text),
            style=discord.ButtonStyle.secondary,
            disabled=True,
        )
    )
    for btn in buttons:
        row.add_item(btn)
    return row


def _avatar_url(user_id: int, member: discord.Member | None) -> str:
    """Small avatar URL (Discord CDN size bucket)."""
    if member is not None:
        return member.display_avatar.with_size(32).url
    return f"https://cdn.discordapp.com/embed/avatars/{(user_id >> 22) % 6}.png?size=32"


def _assignee_heading(user_id: int, member: discord.Member | None) -> discord.ui.Item:
    """Heading with nick (no @) and compact profile icon."""
    name = member.display_name if member is not None else f"User {user_id}"
    # Section: text + thumbnail accessory (Discord always places the accessory
    # opposite the text; 32px CDN asset keeps the icon compact).
    return discord.ui.Section(
        f"## {name}'s Tasks",
        accessory=discord.ui.Thumbnail(_avatar_url(user_id, member), description=name),
    )


async def _resolve_member(
    discord_guild: discord.Guild | None, user_id: int
) -> discord.Member | None:
    if discord_guild is None:
        return None
    member = discord_guild.get_member(user_id)
    if member is not None:
        return member
    try:
        return await discord_guild.fetch_member(user_id)
    except discord.HTTPException:
        return None


async def build_public_tasklist_view(
    guild_id: int,
    *,
    discord_guild: discord.Guild | None = None,
) -> discord.ui.LayoutView:
    from views import DropButton, MarkDoneButton, NewTaskButton, PickupButton

    state = load_state()
    guild = get_guild(state, guild_id)
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.TextDisplay("# Tasks"))

    budget = MAX_LAYOUT_COMPONENTS - 5  # footer + new-task + truncation headroom
    truncated = False

    # --- Unassigned ---
    unassigned = svc.unassigned_tasks(guild)
    un_items: list[discord.ui.Item] = [discord.ui.TextDisplay("## Unassigned")]
    if not unassigned:
        un_items.append(discord.ui.TextDisplay("_None_"))
    else:
        for i, task in enumerate(unassigned, start=1):
            if _count_items(view) + len(un_items) + 3 >= budget:
                un_items.append(
                    discord.ui.TextDisplay(f"_…and {len(unassigned) - i + 1} more unassigned_")
                )
                truncated = True
                break
            un_items.append(
                _task_section(
                    f"{i}. {task['description']}",
                    PickupButton(task["id"]),
                )
            )
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

            member = await _resolve_member(discord_guild, user_id)
            section_items: list[discord.ui.Item] = [_assignee_heading(user_id, member)]
            has_incomplete = False
            for n, task in enumerate(tasks, start=1):
                if task.get("completed"):
                    section_items.append(
                        discord.ui.TextDisplay(f"{n}. ~~{task['description']}~~ ✅")
                    )
                else:
                    has_incomplete = True
                    section_items.append(
                        _task_section(
                            f"{n}. {task['description']}",
                            DropButton(task["id"], source="pub"),
                            MarkDoneButton(task["id"], source="pub"),
                        )
                    )

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
    new_row = discord.ui.ActionRow()
    new_row.add_item(NewTaskButton())
    view.add_item(new_row)
    view.add_item(discord.ui.TextDisplay("Please Handle"))
    return view


def build_mytasks_view(guild_id: int, user_id: int) -> discord.ui.LayoutView:
    from views import DropButton, MarkDoneButton

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
            view.add_item(discord.ui.TextDisplay(f"{i}. ~~{task['description']}~~ ✅"))
        else:
            view.add_item(
                _task_section(
                    f"{i}. {task['description']}",
                    DropButton(task["id"], source="priv"),
                    MarkDoneButton(task["id"], source="priv"),
                )
            )
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
