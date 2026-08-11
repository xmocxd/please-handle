from __future__ import annotations

import logging

import discord
from discord.ext import tasks

import tasks_service as svc
from announce import run_announce_for_guild
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
            state = load_state()
            guild = get_guild(state, guild_id)
            if not svc.should_announce(guild):
                continue

            posted = await run_announce_for_guild(self.bot, guild_id, mark_announced=True)
            if posted:
                log.info("Announced outstanding tasks for guild %s (%s channel(s))", guild_id, posted)

    @loop.before_loop
    async def before_loop(self) -> None:
        await self.bot.wait_until_ready()
