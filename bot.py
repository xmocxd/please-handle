from __future__ import annotations

import logging
import sys

import discord
from discord.ext import commands

from commands_handle import setup_handle_commands
from commands_tasks import setup_task_commands
from config import DISCORD_TOKEN
from scheduler import AnnounceScheduler
from views import DYNAMIC_ITEMS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("please-handle")


class PleaseHandleBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.announce_scheduler = AnnounceScheduler(self)

    async def setup_hook(self) -> None:
        self.add_dynamic_items(*DYNAMIC_ITEMS)
        await setup_task_commands(self.tree)
        await setup_handle_commands(self.tree)
        synced = await self.tree.sync()
        log.info("Synced %s application command(s)", len(synced))
        self.announce_scheduler.start()

    async def on_ready(self) -> None:
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "?")


def main() -> None:
    if not DISCORD_TOKEN:
        print("Set DISCORD_TOKEN in .env", file=sys.stderr)
        sys.exit(1)
    bot = PleaseHandleBot()
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
