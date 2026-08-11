from __future__ import annotations

import logging
from typing import Iterable

import discord

import tasks_service as svc
from storage import get_guild, load_state

log = logging.getLogger("please-handle.announce")

NO_OUTSTANDING_MESSAGE = (
    "No tasks outstanding... handled :3\n"
    "https://tenor.com/view/acchi-kocchi-tsumiki-miniwa-spinning-anime-cute-gif-9172478568670808815"
)


def incomplete_tasks_for_user(guild: dict, user_id: int) -> list[dict]:
    return [t for t in svc.user_tasks(guild, user_id) if not t.get("completed")]


async def send_no_outstanding_announce(channel: discord.abc.Messageable) -> None:
    await channel.send(NO_OUTSTANDING_MESSAGE)


def build_user_outstanding_view(user_id: int, count: int) -> discord.ui.LayoutView:
    from views import MyTasksCountButton

    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.TextDisplay(f"<@{user_id}> you have"))
    row = discord.ui.ActionRow()
    row.add_item(MyTasksCountButton(user_id, count))
    view.add_item(row)
    view.add_item(discord.ui.TextDisplay("outstanding tasks... please handle"))
    return view


def build_open_tasks_announce_view(count: int) -> discord.ui.LayoutView:
    from views import OpenTasksCountButton

    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.TextDisplay("There are"))
    row = discord.ui.ActionRow()
    row.add_item(OpenTasksCountButton(count))
    view.add_item(row)
    view.add_item(discord.ui.TextDisplay("open tasks."))
    return view


async def post_outstanding_announce(
    channel: discord.abc.Messageable,
    guild_id: int,
) -> None:
    """Post scheduled-style outstanding-task reminders to one channel."""
    state = load_state()
    guild = get_guild(state, guild_id)

    outstanding_users: list[tuple[int, int]] = []
    for user_id in svc.assignees_in_order(guild):
        n = len(incomplete_tasks_for_user(guild, user_id))
        if n > 0:
            outstanding_users.append((user_id, n))

    open_count = len(svc.unassigned_tasks(guild))

    if not outstanding_users and open_count == 0:
        await send_no_outstanding_announce(channel)
        return

    for user_id, count in outstanding_users:
        await channel.send(view=build_user_outstanding_view(user_id, count))

    if open_count > 0:
        await channel.send(view=build_open_tasks_announce_view(open_count))


async def run_announce_for_guild(
    bot: discord.Client,
    guild_id: int,
    *,
    channel_ids: Iterable[int] | None = None,
    mark_announced: bool = True,
) -> int:
    """
    Purge aged completed tasks, then post outstanding announces.
    Returns number of channels posted to.
    """
    purged = svc.purge_completed(guild_id)
    if purged:
        log.info("Guild %s purged %s task(s) before announce", guild_id, len(purged))

    state = load_state()
    guild = get_guild(state, guild_id)
    if channel_ids is None:
        channel_ids = list(guild["settings"].get("enabled_channel_ids") or [])

    posted = 0
    for channel_id in channel_ids:
        channel = bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await bot.fetch_channel(channel_id)
            except discord.HTTPException:
                log.warning("Could not fetch channel %s", channel_id)
                continue
        if not isinstance(channel, discord.abc.Messageable):
            continue
        try:
            await post_outstanding_announce(channel, guild_id)
            posted += 1
        except discord.HTTPException as e:
            log.warning("Failed to announce in %s: %s", channel_id, e)

    if mark_announced and posted:
        date_str = svc.guild_now(get_guild(load_state(), guild_id)).date().isoformat()
        svc.mark_announced(guild_id, date_str)

    return posted
