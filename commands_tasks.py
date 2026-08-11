from __future__ import annotations

import discord
from discord import app_commands

import tasks_service as svc
from render import build_mytasks_view, build_public_tasklist_view
from views import _publish_or_update_daily_digest


def _guild_id(interaction: discord.Interaction) -> int:
    if interaction.guild_id is None:
        raise svc.ServiceError("This command only works in a server.")
    return interaction.guild_id


async def setup_task_commands(tree: app_commands.CommandTree) -> None:
    @tree.command(name="tasklist", description="Print the current public task list")
    async def tasklist(interaction: discord.Interaction) -> None:
        try:
            gid = _guild_id(interaction)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        view = build_public_tasklist_view(gid)
        await interaction.response.send_message(view=view)

    @tree.command(name="pickup", description="Pick up an unassigned task by number")
    @app_commands.describe(task_number="Number from the unassigned list")
    async def pickup(interaction: discord.Interaction, task_number: app_commands.Range[int, 1, 999]) -> None:
        try:
            gid = _guild_id(interaction)
            task = svc.pickup_task(gid, interaction.user.id, task_number)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await interaction.response.send_message(
            f"{interaction.user.mention} picked up **{task['description']}**."
        )

    @tree.command(name="putdown", description="Put down one of your assigned tasks")
    @app_commands.describe(task_number="Number from your own task list")
    async def putdown(interaction: discord.Interaction, task_number: app_commands.Range[int, 1, 999]) -> None:
        try:
            gid = _guild_id(interaction)
            task = svc.putdown_task(gid, interaction.user.id, task_number)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await interaction.response.send_message(
            f"{interaction.user.mention} put down **{task['description']}**."
        )

    @tree.command(name="mytasks", description="Show your assigned tasks (only you can see this)")
    async def mytasks(interaction: discord.Interaction) -> None:
        try:
            gid = _guild_id(interaction)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        view = build_mytasks_view(gid, interaction.user.id)
        await interaction.response.send_message(view=view, ephemeral=True)

    @tree.command(name="markdone", description="Mark one of your assigned tasks complete")
    @app_commands.describe(task_number="Number from your own task list")
    async def markdone(interaction: discord.Interaction, task_number: app_commands.Range[int, 1, 999]) -> None:
        try:
            gid = _guild_id(interaction)
            task = svc.mark_done(gid, interaction.user.id, task_number)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        # Acknowledge privately so we can post/edit the public daily digest.
        await interaction.response.defer(ephemeral=True)
        await _publish_or_update_daily_digest(
            interaction, gid, interaction.user, task["description"]
        )
        await interaction.followup.send("Marked done.", ephemeral=True)

    @tree.command(name="newtask", description="Add a new unassigned task")
    @app_commands.describe(description="What needs to be done")
    async def newtask(interaction: discord.Interaction, description: str) -> None:
        try:
            gid = _guild_id(interaction)
            task = svc.new_task(gid, description)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await interaction.response.send_message(
            f"Added unassigned task: **{task['description']}**."
        )

    @tree.command(name="assign", description="Assign an unassigned task to a user")
    @app_commands.describe(task_number="Number from the unassigned list", user="Who should own it")
    async def assign(
        interaction: discord.Interaction,
        task_number: app_commands.Range[int, 1, 999],
        user: discord.Member,
    ) -> None:
        try:
            gid = _guild_id(interaction)
            task = svc.assign_task(gid, task_number, user.id)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await interaction.response.send_message(
            f"Assigned **{task['description']}** to {user.mention}."
        )

    @tree.command(name="unassign", description="Unassign a task from a user's list")
    @app_commands.describe(user="Whose list", task_number="Number on that user's list")
    async def unassign(
        interaction: discord.Interaction,
        user: discord.Member,
        task_number: app_commands.Range[int, 1, 999],
    ) -> None:
        try:
            gid = _guild_id(interaction)
            task = svc.unassign_task(gid, user.id, task_number)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await interaction.response.send_message(
            f"Unassigned **{task['description']}** from {user.mention}."
        )

    @tree.command(name="removetask", description="Delete a task from the unassigned list")
    @app_commands.describe(task_number="Number from the unassigned list")
    async def removetask(interaction: discord.Interaction, task_number: app_commands.Range[int, 1, 999]) -> None:
        try:
            gid = _guild_id(interaction)
            task = svc.remove_task(gid, task_number)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await interaction.response.send_message(
            f"Removed unassigned task: **{task['description']}**."
        )
