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
        self._commands_synced = False

    async def setup_hook(self) -> None:
        self.add_dynamic_items(*DYNAMIC_ITEMS)
        await setup_task_commands(self.tree)
        await setup_handle_commands(self.tree)
        self.announce_scheduler.start()

    async def force_sync_commands(self) -> None:
        """Copy the command tree onto every guild and sync immediately.

        Guild-scoped sync is visible right away; a global-only sync can take up
        to ~1 hour to show in the Discord client. After guild sync, clear any
        previously published global commands so the client does not show
        duplicates (old global + new guild).
        """
        guilds = list(self.guilds)
        if not guilds:
            log.warning("No guilds available to sync commands to yet")
            return

        for guild in guilds:
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            names = ", ".join(sorted({c.name for c in synced}))
            log.info(
                "Force-synced %s command(s) to guild %s (%s): %s",
                len(synced),
                guild.name,
                guild.id,
                names or "(none)",
            )

        # Drop remote global commands (keep local tree + guild copies intact).
        preserved = list(self.tree.get_commands())
        self.tree.clear_commands(guild=None)
        await self.tree.sync()
        for cmd in preserved:
            self.tree.add_command(cmd)
        log.info("Cleared global application commands (guild sync is source of truth)")

    async def on_ready(self) -> None:
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "?")
        if self._commands_synced:
            return
        self._commands_synced = True
        try:
            await self.force_sync_commands()
        except Exception:
            log.exception("Failed to force-sync application commands")
            self._commands_synced = False

    async def on_guild_join(self, guild: discord.Guild) -> None:
        try:
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info(
                "Force-synced %s command(s) to new guild %s (%s)",
                len(synced),
                guild.name,
                guild.id,
            )
        except Exception:
            log.exception("Failed to sync commands for new guild %s", guild.id)


def main() -> None:
    if not DISCORD_TOKEN:
        print("Set DISCORD_TOKEN in .env", file=sys.stderr)
        sys.exit(1)
    bot = PleaseHandleBot()
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
