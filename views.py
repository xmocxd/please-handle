from __future__ import annotations

import re
from typing import Literal

import discord

import tasks_service as svc
from render import build_mytasks_view, build_public_tasklist_view
from storage import get_guild, load_state

Source = Literal["pub", "priv"]


async def _require_guild(interaction: discord.Interaction) -> int:
    if interaction.guild_id is None:
        await interaction.response.send_message("This only works in a server.", ephemeral=True)
        raise RuntimeError("no guild")
    return interaction.guild_id


async def _publish_or_update_daily_digest(
    interaction: discord.Interaction,
    guild_id: int,
    user: discord.abc.User,
    completed_description: str,
) -> None:
    """Public once-per-day completion message with updated personal list (slash / mytasks)."""
    state = load_state()
    guild = get_guild(state, guild_id)
    date_str = svc.guild_now(guild).date().isoformat()
    task_block = svc.format_user_task_list(guild, user.id)
    body = (
        f"{user.mention} completed **{completed_description}**\n\n"
        f"## Your Tasks:\n{task_block}"
    )

    existing = svc.get_daily_completion_msg(guild_id, user.id, date_str)
    channel = interaction.channel
    if channel is None or not hasattr(channel, "send"):
        return

    if existing:
        try:
            ch = interaction.guild.get_channel(existing["channel_id"]) if interaction.guild else None
            if ch is None:
                ch = channel
            msg = await ch.fetch_message(existing["message_id"])
            await msg.edit(content=body)
            return
        except (discord.NotFound, discord.HTTPException, AttributeError):
            pass

    sent = await channel.send(content=body)
    svc.set_daily_completion_msg(guild_id, user.id, date_str, sent.channel.id, sent.id)


class NewTaskModal(discord.ui.Modal, title="New Task"):
    description = discord.ui.TextInput(
        label="Description",
        placeholder="What needs to be done?",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("This only works in a server.", ephemeral=True)
            return
        try:
            task = svc.new_task(interaction.guild_id, str(self.description.value))
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        view = await build_public_tasklist_view(
            interaction.guild_id, discord_guild=interaction.guild
        )
        # Refresh the public list message this button lived on, when possible.
        if interaction.message is not None:
            await interaction.response.edit_message(view=view)
            await interaction.followup.send(
                f"Added unassigned task: **{task['description']}**.",
            )
        else:
            await interaction.response.send_message(
                f"Added unassigned task: **{task['description']}**.",
            )


class NewTaskButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ph:newtask",
):
    def __init__(self) -> None:
        super().__init__(
            discord.ui.Button(
                label="New Task",
                emoji="➕",
                style=discord.ButtonStyle.success,
                custom_id="ph:newtask",
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ):
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(NewTaskModal())


class PickupButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ph:pickup:(?P<task_id>[0-9a-fA-F-]{36})",
):
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        super().__init__(
            discord.ui.Button(
                label="Pick Up",
                emoji="📥",
                style=discord.ButtonStyle.primary,
                custom_id=f"ph:pickup:{task_id}",
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ):
        return cls(match["task_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            guild_id = await _require_guild(interaction)
        except RuntimeError:
            return
        try:
            task = svc.pickup_task_by_id(guild_id, interaction.user.id, self.task_id)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        view = await build_public_tasklist_view(guild_id, discord_guild=interaction.guild)
        await interaction.response.edit_message(view=view)
        await interaction.followup.send(
            f"{interaction.user.mention} picked up **{task['description']}**.",
        )


class DropButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ph:drop:(?P<source>pub|priv):(?P<task_id>[0-9a-fA-F-]{36})",
):
    def __init__(self, task_id: str, source: Source = "pub") -> None:
        self.task_id = task_id
        self.source: Source = source
        super().__init__(
            discord.ui.Button(
                label="Drop",
                emoji="📤",
                style=discord.ButtonStyle.secondary,
                custom_id=f"ph:drop:{source}:{task_id}",
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ):
        return cls(match["task_id"], source=match["source"])  # type: ignore[arg-type]

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            guild_id = await _require_guild(interaction)
        except RuntimeError:
            return

        state = load_state()
        guild = get_guild(state, guild_id)
        task = svc.get_task_by_id(guild, self.task_id)
        if task is None:
            await interaction.response.send_message("Task not found.", ephemeral=True)
            return
        if task.get("assignee_id") != interaction.user.id:
            await interaction.response.send_message(
                "Only the assignee can drop this task.", ephemeral=True
            )
            return

        try:
            task = svc.drop_task_by_id(guild_id, interaction.user.id, self.task_id)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        if self.source == "priv":
            view = build_mytasks_view(guild_id, interaction.user.id)
            await interaction.response.edit_message(view=view)
            await interaction.followup.send(
                f"{interaction.user.mention} dropped **{task['description']}**.",
            )
        else:
            view = await build_public_tasklist_view(guild_id, discord_guild=interaction.guild)
            await interaction.response.edit_message(view=view)
            await interaction.followup.send(
                f"{interaction.user.mention} dropped **{task['description']}**.",
            )


class MarkDoneButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ph:done:(?P<source>pub|priv):(?P<task_id>[0-9a-fA-F-]{36})",
):
    def __init__(self, task_id: str, source: Source = "pub") -> None:
        self.task_id = task_id
        self.source: Source = source
        super().__init__(
            discord.ui.Button(
                label="Done",
                emoji="✅",
                style=discord.ButtonStyle.success,
                custom_id=f"ph:done:{source}:{task_id}",
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
        /,
    ):
        return cls(match["task_id"], source=match["source"])  # type: ignore[arg-type]

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            guild_id = await _require_guild(interaction)
        except RuntimeError:
            return

        state = load_state()
        guild = get_guild(state, guild_id)
        task = svc.get_task_by_id(guild, self.task_id)
        if task is None:
            await interaction.response.send_message("Task not found.", ephemeral=True)
            return
        if task.get("assignee_id") != interaction.user.id:
            await interaction.response.send_message(
                "Only the assignee can mark this task done.", ephemeral=True
            )
            return

        try:
            task = svc.mark_done_by_id(guild_id, interaction.user.id, self.task_id)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        desc = task["description"]
        if self.source == "priv":
            view = build_mytasks_view(guild_id, interaction.user.id)
            await interaction.response.edit_message(view=view)
            await _publish_or_update_daily_digest(interaction, guild_id, interaction.user, desc)
        else:
            view = await build_public_tasklist_view(guild_id, discord_guild=interaction.guild)
            await interaction.response.edit_message(view=view)
            await interaction.followup.send(
                f"{interaction.user.mention} completed **{desc}**.",
            )


DYNAMIC_ITEMS = (PickupButton, DropButton, MarkDoneButton, NewTaskButton)
