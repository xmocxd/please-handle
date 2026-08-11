from __future__ import annotations

import re
from typing import Literal

import discord

import tasks_service as svc
from render import (
    build_assignee_view,
    build_mytasks_view,
    build_unassigned_view,
    refresh_public_lists,
)
from storage import get_guild, load_state

Source = Literal["pub", "priv"]
ShowMoreKind = Literal["u", "a", "m"]


async def _require_guild(interaction: discord.Interaction) -> int:
    if interaction.guild_id is None:
        await interaction.response.send_message("This only works in a server.", ephemeral=True)
        raise RuntimeError("no guild")
    return interaction.guild_id


async def _silent_ack(interaction: discord.Interaction) -> None:
    """Acknowledge without leaving a visible success message."""
    if interaction.response.is_done():
        return
    await interaction.response.defer(ephemeral=True)
    try:
        await interaction.delete_original_response()
    except discord.HTTPException:
        pass


async def _publish_or_update_daily_digest(
    interaction: discord.Interaction,
    guild_id: int,
    user: discord.abc.User,
    completed_description: str,
) -> None:
    """Public once-per-day completion message with updated personal list."""
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
            svc.new_task(interaction.guild_id, str(self.description.value))
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        view = build_unassigned_view(interaction.guild_id, offset=0)
        if interaction.message is not None:
            await interaction.response.edit_message(view=view)
        else:
            await _silent_ack(interaction)


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


class ShowMoreButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ph:more:(?P<kind>u|a|m):(?P<key>[0-9]+):(?P<offset>[0-9]+)",
):
    def __init__(self, kind: ShowMoreKind, key: int, offset: int) -> None:
        self.kind = kind
        self.key = key
        self.offset = offset
        super().__init__(
            discord.ui.Button(
                label="Show more",
                emoji="⬇️",
                style=discord.ButtonStyle.primary,
                custom_id=f"ph:more:{kind}:{key}:{offset}",
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
        return cls(match["kind"], int(match["key"]), int(match["offset"]))  # type: ignore[arg-type]

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            guild_id = await _require_guild(interaction)
        except RuntimeError:
            return

        if self.kind == "u":
            view = build_unassigned_view(guild_id, offset=self.offset)
        elif self.kind == "a":
            view = await build_assignee_view(
                guild_id, self.key, discord_guild=interaction.guild, offset=self.offset
            )
        else:
            if interaction.user.id != self.key:
                await interaction.response.send_message(
                    "This list is not yours.", ephemeral=True
                )
                return
            view = build_mytasks_view(guild_id, self.key, offset=self.offset)

        await interaction.response.edit_message(view=view)


class MyTasksCountButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ph:mycount:(?P<user_id>[0-9]+):(?P<count>[0-9]+)",
):
    """Announce button: shows the assignee their /mytasks list."""

    def __init__(self, user_id: int, count: int) -> None:
        self.user_id = user_id
        self.count = count
        super().__init__(
            discord.ui.Button(
                label=str(count),
                style=discord.ButtonStyle.primary,
                custom_id=f"ph:mycount:{user_id}:{count}",
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
        return cls(int(match["user_id"]), int(match["count"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            guild_id = await _require_guild(interaction)
        except RuntimeError:
            return
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Only the mentioned user can open this task list.",
                ephemeral=True,
            )
            return
        view = build_mytasks_view(guild_id, self.user_id, offset=0)
        await interaction.response.send_message(view=view, ephemeral=True)


class OpenTasksCountButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ph:opencount:(?P<count>[0-9]+)",
):
    """Announce button: posts the /opentasks unassigned list."""

    def __init__(self, count: int) -> None:
        self.count = count
        super().__init__(
            discord.ui.Button(
                label=str(count),
                style=discord.ButtonStyle.primary,
                custom_id=f"ph:opencount:{count}",
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
        return cls(int(match["count"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            guild_id = await _require_guild(interaction)
        except RuntimeError:
            return
        view = build_unassigned_view(guild_id, offset=0)
        await interaction.response.send_message(view=view)
        msg = await interaction.original_response()
        svc.update_public_list_unassigned_msg(guild_id, msg.channel.id, msg.id)


class DescriptionButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ph:desc:(?P<task_id>[0-9a-fA-F-]{36})",
):
    """Clickable task label — shows full description ephemerally (URLs can embed)."""

    def __init__(self, task_id: str, *, label: str) -> None:
        self.task_id = task_id
        super().__init__(
            discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                custom_id=f"ph:desc:{task_id}",
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
        # Label comes from the message component; use a placeholder for reconstruction.
        return cls(match["task_id"], label=item.label or "Task")

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
        await interaction.response.send_message(
            task["description"],
            ephemeral=True,
            suppress_embeds=False,
        )


class AssignUserSelect(discord.ui.UserSelect):
    def __init__(self, task_id: str, guild_id: int) -> None:
        super().__init__(
            placeholder="Select a user to assign…",
            min_values=1,
            max_values=1,
        )
        self.task_id = task_id
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction) -> None:
        user = self.values[0]
        if user.bot:
            await interaction.response.send_message(
                "Cannot assign tasks to bots.", ephemeral=True
            )
            return
        try:
            task = svc.assign_task_by_id(self.guild_id, self.task_id, user.id)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        await interaction.response.edit_message(
            content=f"Assigned **{task['description']}** to {user.mention}.",
            view=None,
        )
        await interaction.followup.send(
            f"Assigned **{task['description']}** to {user.mention}.",
        )
        await refresh_public_lists(
            interaction.client,
            self.guild_id,
            discord_guild=interaction.guild,
            unassigned=True,
            user_ids=[user.id],
        )


class AssignUserView(discord.ui.View):
    def __init__(self, task_id: str, guild_id: int) -> None:
        super().__init__(timeout=120)
        self.add_item(AssignUserSelect(task_id, guild_id))


class AssignButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ph:assign:(?P<task_id>[0-9a-fA-F-]{36})",
):
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        super().__init__(
            discord.ui.Button(
                label="Assign",
                emoji="👤",
                style=discord.ButtonStyle.secondary,
                custom_id=f"ph:assign:{task_id}",
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
        state = load_state()
        guild = get_guild(state, guild_id)
        task = svc.get_task_by_id(guild, self.task_id)
        if task is None:
            await interaction.response.send_message("Task not found.", ephemeral=True)
            return
        if task.get("assignee_id") is not None:
            await interaction.response.send_message(
                "That task is already assigned.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"Assign **{task['description']}** to:",
            view=AssignUserView(self.task_id, guild_id),
            ephemeral=True,
        )


class PickupButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"ph:pickup:(?P<task_id>[0-9a-fA-F-]{36})",
):
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        super().__init__(
            discord.ui.Button(
                label="Pick Up",
                emoji="📤",
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

        view = build_unassigned_view(guild_id, offset=0)
        await interaction.response.edit_message(view=view)
        await interaction.followup.send(
            f"{interaction.user.mention} picked up **{task['description']}**.",
        )
        await refresh_public_lists(
            interaction.client,
            guild_id,
            discord_guild=interaction.guild,
            user_ids=[interaction.user.id],
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
                emoji="📥",
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

        desc = task["description"]
        if self.source == "priv":
            view = build_mytasks_view(guild_id, interaction.user.id, offset=0)
            await interaction.response.edit_message(view=view)
            await interaction.followup.send(
                f"{interaction.user.mention} dropped **{desc}**.",
            )
            await refresh_public_lists(
                interaction.client,
                guild_id,
                discord_guild=interaction.guild,
                unassigned=True,
                user_ids=[interaction.user.id],
            )
        else:
            view = await build_assignee_view(
                guild_id,
                interaction.user.id,
                discord_guild=interaction.guild,
                offset=0,
            )
            await interaction.response.edit_message(view=view)
            await interaction.followup.send(
                f"{interaction.user.mention} dropped **{desc}**.",
            )
            await refresh_public_lists(
                interaction.client,
                guild_id,
                discord_guild=interaction.guild,
                unassigned=True,
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
            view = build_mytasks_view(guild_id, interaction.user.id, offset=0)
            await interaction.response.edit_message(view=view)
            await _publish_or_update_daily_digest(interaction, guild_id, interaction.user, desc)
            await refresh_public_lists(
                interaction.client,
                guild_id,
                discord_guild=interaction.guild,
                user_ids=[interaction.user.id],
            )
        else:
            view = await build_assignee_view(
                guild_id,
                interaction.user.id,
                discord_guild=interaction.guild,
                offset=0,
            )
            await interaction.response.edit_message(view=view)
            await interaction.followup.send(
                f"{interaction.user.mention} completed **{desc}**.",
            )
            await refresh_public_lists(
                interaction.client,
                guild_id,
                discord_guild=interaction.guild,
                user_ids=[interaction.user.id],
            )


DYNAMIC_ITEMS = (
    MyTasksCountButton,
    OpenTasksCountButton,
    DescriptionButton,
    PickupButton,
    AssignButton,
    DropButton,
    MarkDoneButton,
    NewTaskButton,
    ShowMoreButton,
)
