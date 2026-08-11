from __future__ import annotations

import logging

import discord
from discord.ext import tasks

import tasks_service as svc
from render import build_public_tasklist_view
from storage import get_guild, load_state

log = logging.getLogger("please-handle.scheduler")


class AnnounceScheduler:
    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot

    def start(self) -> None:
        if not self.loop.is_running():
            self.loop.start()

    def stop(self) -> None:
        if self.loop.is_running():
            self.loop.cancel()

    @tasks.loop(minutes=1)
    async def loop(self) -> None:
        state = load_state()
        for guild_key, _guild_data in list(state.get("guilds", {}).items()):
            try:
                guild_id = int(guild_key)
            except ValueError:
                continue
            # Reload fresh guild slice each iteration
            state = load_state()
            guild = get_guild(state, guild_id)
            if not svc.should_announce(guild):
                continue

            purged = svc.purge_completed(guild_id)
            if purged:
                log.info("Guild %s auto-purged %s task(s)", guild_id, len(purged))

            state = load_state()
            guild = get_guild(state, guild_id)
            date_str = svc.guild_now(guild).date().isoformat()
            channel_ids = list(guild["settings"].get("enabled_channel_ids") or [])

            for channel_id in channel_ids:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except discord.HTTPException:
                        log.warning("Could not fetch channel %s", channel_id)
                        continue
                if not isinstance(channel, discord.abc.Messageable):
                    continue
                try:
                    await channel.send(view=build_public_tasklist_view(guild_id))
                except discord.HTTPException as e:
                    log.warning("Failed to announce in %s: %s", channel_id, e)

            svc.mark_announced(guild_id, date_str)
            log.info("Announced task list for guild %s on %s", guild_id, date_str)

    @loop.before_loop
    async def before_loop(self) -> None:
        await self.bot.wait_until_ready()
