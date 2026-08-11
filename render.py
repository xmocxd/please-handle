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
    """Nested component count for Discord's LayoutView limit."""

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


def _task_section(task_id: str, text: str, *buttons: discord.ui.Item) -> discord.ui.Item:
    """Description button (click for full text) + action button(s) on one row."""
    from views import DescriptionButton

    row = discord.ui.ActionRow()
    row.add_item(DescriptionButton(task_id, label=_truncate_label(text)))
    for btn in buttons:
        row.add_item(btn)
    return row


def _avatar_url(user_id: int, member: discord.Member | None) -> str:
    if member is not None:
        return member.display_avatar.with_size(64).url
    return f"https://cdn.discordapp.com/embed/avatars/{(user_id >> 22) % 6}.png?size=64"


def _assignee_heading(user_id: int, member: discord.Member | None) -> discord.ui.Item:
    name = member.display_name if member is not None else f"User {user_id}"
    return discord.ui.Section(
        f"### {name}'s Tasks",
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


def build_unassigned_view(guild_id: int, *, offset: int = 0) -> discord.ui.LayoutView:
    from views import AssignButton, NewTaskButton, PickupButton, ShowMoreButton

    state = load_state()
    guild = get_guild(state, guild_id)
    tasks = svc.unassigned_tasks(guild)

    view = discord.ui.LayoutView(timeout=None)
    if offset == 0:
        view.add_item(discord.ui.TextDisplay("Please Handle"))

    body: list[discord.ui.Item] = [discord.ui.TextDisplay("### Unassigned Tasks")]
    if not tasks:
        body.append(discord.ui.TextDisplay("_None_"))
        view.add_item(discord.ui.Container(*body, accent_colour=COLOR_UNASSIGNED))
        row = discord.ui.ActionRow()
        row.add_item(NewTaskButton())
        view.add_item(row)
        return view

    if offset > 0:
        body.append(discord.ui.TextDisplay(f"_Continuing from #{offset + 1}_"))

    task_items: list[discord.ui.Item] = []
    for i, task in enumerate(tasks):
        if i < offset:
            continue
        task_items.append(
            _task_section(
                task["id"],
                f"{i + 1}. {task['description']}",
                PickupButton(task["id"]),
                AssignButton(task["id"]),
            )
        )

    packed_body = list(body)
    consumed = 0
    while consumed < len(task_items):
        trial_body = packed_body + [task_items[consumed]]
        remaining_after = len(task_items) - (consumed + 1)
        probe = discord.ui.LayoutView(timeout=None)
        try:
            for it in view.children:
                probe.add_item(it)
            probe.add_item(discord.ui.Container(*trial_body, accent_colour=COLOR_UNASSIGNED))
            if remaining_after > 0:
                r = discord.ui.ActionRow()
                r.add_item(ShowMoreButton(kind="u", key=0, offset=offset + consumed + 1))
                probe.add_item(r)
            r_new = discord.ui.ActionRow()
            r_new.add_item(NewTaskButton())
            probe.add_item(r_new)
        except ValueError:
            break
        if _count_items(probe) > MAX_LAYOUT_COMPONENTS:
            break
        packed_body.append(task_items[consumed])
        consumed += 1

    if consumed == 0 and task_items:
        packed_body.append(task_items[0])
        consumed = 1

    view.add_item(discord.ui.Container(*packed_body, accent_colour=COLOR_UNASSIGNED))
    next_offset = offset + consumed
    if next_offset < len(tasks):
        r = discord.ui.ActionRow()
        r.add_item(ShowMoreButton(kind="u", key=0, offset=next_offset))
        view.add_item(r)
    r_new = discord.ui.ActionRow()
    r_new.add_item(NewTaskButton())
    view.add_item(r_new)
    return view


async def build_assignee_view(
    guild_id: int,
    user_id: int,
    *,
    discord_guild: discord.Guild | None = None,
    member: discord.Member | None = None,
    offset: int = 0,
) -> discord.ui.LayoutView:
    from views import DropButton, MarkDoneButton, ShowMoreButton

    state = load_state()
    guild = get_guild(state, guild_id)
    tasks = svc.user_tasks(guild, user_id)
    if member is None:
        member = await _resolve_member(discord_guild, user_id)

    view = discord.ui.LayoutView(timeout=None)
    body: list[discord.ui.Item] = [_assignee_heading(user_id, member)]
    if offset > 0:
        body.append(discord.ui.TextDisplay(f"_Continuing from #{offset + 1}_"))

    has_incomplete = any(not t.get("completed") for t in tasks)
    accent = COLOR_ASSIGNED if has_incomplete else COLOR_COMPLETE

    if not tasks:
        body.append(discord.ui.TextDisplay("_No tasks._"))
        view.add_item(discord.ui.Container(*body, accent_colour=accent))
        return view

    task_items: list[discord.ui.Item] = []
    for i, task in enumerate(tasks):
        if i < offset:
            continue
        if task.get("completed"):
            task_items.append(
                _task_section(
                    task["id"],
                    f"{i + 1}. ✅ {task['description']}",
                )
            )
        else:
            task_items.append(
                _task_section(
                    task["id"],
                    f"{i + 1}. {task['description']}",
                    DropButton(task["id"], source="pub"),
                    MarkDoneButton(task["id"], source="pub"),
                )
            )

    packed_body = list(body)
    consumed = 0
    while consumed < len(task_items):
        trial_body = packed_body + [task_items[consumed]]
        remaining_after = len(task_items) - (consumed + 1)
        probe = discord.ui.LayoutView(timeout=None)
        try:
            probe.add_item(discord.ui.Container(*trial_body, accent_colour=accent))
            if remaining_after > 0:
                r = discord.ui.ActionRow()
                r.add_item(ShowMoreButton(kind="a", key=user_id, offset=offset + consumed + 1))
                probe.add_item(r)
        except ValueError:
            break
        if _count_items(probe) > MAX_LAYOUT_COMPONENTS:
            break
        packed_body.append(task_items[consumed])
        consumed += 1

    if consumed == 0 and task_items:
        packed_body.append(task_items[0])
        consumed = 1

    view.add_item(discord.ui.Container(*packed_body, accent_colour=accent))
    next_offset = offset + consumed
    if next_offset < len(tasks):
        r = discord.ui.ActionRow()
        r.add_item(ShowMoreButton(kind="a", key=user_id, offset=next_offset))
        view.add_item(r)
    return view


def build_mytasks_view(guild_id: int, user_id: int, *, offset: int = 0) -> discord.ui.LayoutView:
    from views import DropButton, MarkDoneButton, ShowMoreButton

    state = load_state()
    guild = get_guild(state, guild_id)
    tasks = svc.user_tasks(guild, user_id)
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.TextDisplay("## Your Tasks:"))

    if not tasks:
        view.add_item(discord.ui.TextDisplay("_No tasks assigned._"))
        return view

    if offset > 0:
        view.add_item(discord.ui.TextDisplay(f"_Continuing from #{offset + 1}_"))

    task_items: list[discord.ui.Item] = []
    for i, task in enumerate(tasks):
        if i < offset:
            continue
        if task.get("completed"):
            task_items.append(
                _task_section(
                    task["id"],
                    f"{i + 1}. ✅ {task['description']}",
                )
            )
        else:
            task_items.append(
                _task_section(
                    task["id"],
                    f"{i + 1}. {task['description']}",
                    DropButton(task["id"], source="priv"),
                    MarkDoneButton(task["id"], source="priv"),
                )
            )

    consumed = 0
    while consumed < len(task_items):
        probe = discord.ui.LayoutView(timeout=None)
        try:
            for it in view.children:
                probe.add_item(it)
            probe.add_item(task_items[consumed])
            remaining_after = len(task_items) - (consumed + 1)
            if remaining_after > 0:
                r = discord.ui.ActionRow()
                r.add_item(ShowMoreButton(kind="m", key=user_id, offset=offset + consumed + 1))
                probe.add_item(r)
        except ValueError:
            break
        if _count_items(probe) > MAX_LAYOUT_COMPONENTS:
            break
        view.add_item(task_items[consumed])
        consumed += 1

    if consumed == 0 and task_items:
        view.add_item(task_items[0])
        consumed = 1

    next_offset = offset + consumed
    if next_offset < len(tasks):
        r = discord.ui.ActionRow()
        r.add_item(ShowMoreButton(kind="m", key=user_id, offset=next_offset))
        view.add_item(r)
    return view


async def post_public_tasklist(
    destination: discord.abc.Messageable,
    guild_id: int,
    *,
    discord_guild: discord.Guild | None = None,
    interaction: discord.Interaction | None = None,
    start_batch: bool = True,
) -> None:
    """Post unassigned + each assignee as separate messages and remember their IDs.

    start_batch: when True (default), replaces the guild's tracked latest list batch.
    Set False when posting additional channels in the same announce batch.
    """
    if start_batch:
        svc.clear_public_list_msgs(guild_id)

    first = True
    unassigned_message_id: int | None = None
    assignee_message_ids: dict[int, int] = {}
    channel_id: int | None = getattr(destination, "id", None)

    async def _send(view: discord.ui.LayoutView) -> discord.Message:
        nonlocal first
        if first and interaction is not None and not interaction.response.is_done():
            await interaction.response.send_message(view=view)
            msg = await interaction.original_response()
        elif interaction is not None and interaction.response.is_done():
            msg = await interaction.followup.send(view=view, wait=True)
        else:
            msg = await destination.send(view=view)
        first = False
        return msg

    msg = await _send(build_unassigned_view(guild_id, offset=0))
    unassigned_message_id = msg.id
    if channel_id is None:
        channel_id = msg.channel.id

    state = load_state()
    guild = get_guild(state, guild_id)
    for user_id in svc.assignees_in_order(guild):
        if not svc.user_tasks(guild, user_id):
            continue
        member = await _resolve_member(discord_guild, user_id)
        view = await build_assignee_view(
            guild_id, user_id, discord_guild=discord_guild, member=member, offset=0
        )
        msg = await _send(view)
        assignee_message_ids[user_id] = msg.id

    if channel_id is not None and unassigned_message_id is not None:
        svc.record_public_list(
            guild_id,
            channel_id,
            unassigned_message_id=unassigned_message_id,
            assignee_message_ids=assignee_message_ids,
        )


async def hide_public_lists(client: discord.Client, guild_id: int) -> int:
    """Delete all tracked latest public list messages. Returns how many were deleted."""
    targets = svc.iter_public_list_message_ids(guild_id)
    deleted = 0
    for channel_id, message_id in targets:
        channel = client.get_channel(channel_id)
        if channel is None:
            try:
                channel = await client.fetch_channel(channel_id)
            except discord.HTTPException:
                continue
        if not isinstance(channel, discord.abc.Messageable):
            continue
        try:
            msg = await channel.fetch_message(message_id)
            await msg.delete()
            deleted += 1
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            continue
    svc.clear_public_list_msgs(guild_id)
    return deleted


async def refresh_public_lists(
    client: discord.Client,
    guild_id: int,
    *,
    discord_guild: discord.Guild | None = None,
    unassigned: bool = False,
    user_ids: list[int] | None = None,
) -> None:
    """Edit the most recent tracked public list messages after task state changes."""
    user_ids = list(user_ids or [])
    tracked = svc.get_public_list_msgs(guild_id)
    if not tracked:
        return

    for channel_key, entry in tracked.items():
        try:
            channel_id = int(channel_key)
        except ValueError:
            continue
        channel = client.get_channel(channel_id)
        if channel is None:
            try:
                channel = await client.fetch_channel(channel_id)
            except discord.HTTPException:
                continue
        if not isinstance(channel, discord.abc.Messageable):
            continue

        if unassigned:
            mid = entry.get("unassigned_message_id")
            if mid:
                try:
                    msg = await channel.fetch_message(int(mid))
                    await msg.edit(view=build_unassigned_view(guild_id, offset=0))
                except (discord.NotFound, discord.HTTPException):
                    pass

        assignees = dict(entry.get("assignees") or {})
        for uid in user_ids:
            mid = assignees.get(str(uid))
            view = await build_assignee_view(
                guild_id, uid, discord_guild=discord_guild, offset=0
            )
            if mid:
                try:
                    msg = await channel.fetch_message(int(mid))
                    await msg.edit(view=view)
                    continue
                except (discord.NotFound, discord.HTTPException):
                    pass
            # No tracked message (or it was deleted) — post a new assignee list.
            try:
                sent = await channel.send(view=view)
                svc.update_public_list_assignee_msg(guild_id, channel_id, uid, sent.id)
            except discord.HTTPException:
                pass


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
