from __future__ import annotations

import discord
from discord import app_commands

import tasks_service as svc
from announce import run_announce_for_guild
from render import (
    build_mytasks_view,
    build_unassigned_view,
    hide_public_lists,
    post_public_tasklist,
    refresh_public_lists,
)
from storage import get_guild, load_state
from views import _publish_or_update_daily_digest, _silent_ack


def _guild_id(interaction: discord.Interaction) -> int:
    if interaction.guild_id is None:
        raise svc.ServiceError("This command only works in a server.")
    return interaction.guild_id


async def _ack_and_refresh(
    interaction: discord.Interaction,
    guild_id: int,
    *,
    unassigned: bool = False,
    user_ids: list[int] | None = None,
) -> None:
    await _silent_ack(interaction)
    await refresh_public_lists(
        interaction.client,
        guild_id,
        discord_guild=interaction.guild,
        unassigned=unassigned,
        user_ids=user_ids,
    )


async def setup_task_commands(tree: app_commands.CommandTree) -> None:
    @tree.command(name="tasklist", description="Print the full public task list")
    async def tasklist(interaction: discord.Interaction) -> None:
        try:
            gid = _guild_id(interaction)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        channel = interaction.channel
        if channel is None or not isinstance(channel, discord.abc.Messageable):
            await interaction.response.send_message(
                "Cannot post a task list here.", ephemeral=True
            )
            return
        await post_public_tasklist(
            channel, gid, discord_guild=interaction.guild, interaction=interaction
        )

    @tree.command(name="opentasks", description="Print only the unassigned task list")
    async def opentasks(interaction: discord.Interaction) -> None:
        try:
            gid = _guild_id(interaction)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        view = build_unassigned_view(gid, offset=0)
        await interaction.response.send_message(view=view)
        msg = await interaction.original_response()
        svc.update_public_list_unassigned_msg(gid, msg.channel.id, msg.id)

    @tree.command(name="hidelist", description="Delete the most recent public task list posts")
    async def hidelist(interaction: discord.Interaction) -> None:
        try:
            gid = _guild_id(interaction)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        tracked = svc.iter_public_list_message_ids(gid)
        if not tracked:
            await interaction.response.send_message(
                "No tracked task list posts to hide.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        deleted = await hide_public_lists(interaction.client, gid)
        await interaction.followup.send(
            f"Hidden **{deleted}** task list message(s).",
            ephemeral=True,
        )

    @tree.command(
        name="announcetasks",
        description="Force the scheduled outstanding-tasks announcement now",
    )
    async def announcetasks(interaction: discord.Interaction) -> None:
        try:
            gid = _guild_id(interaction)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        state = load_state()
        guild = get_guild(state, gid)
        channel_ids = list(guild["settings"].get("enabled_channel_ids") or [])
        if not channel_ids:
            if interaction.channel_id is None:
                await interaction.response.send_message(
                    "No enabled announce channels. Use `/handle enable` first.",
                    ephemeral=True,
                )
                return
            channel_ids = [interaction.channel_id]

        await interaction.response.defer(ephemeral=True)
        posted = await run_announce_for_guild(
            interaction.client,
            gid,
            channel_ids=channel_ids,
            mark_announced=True,
        )
        await interaction.followup.send(
            f"Announcement posted to **{posted}** channel(s).",
            ephemeral=True,
        )

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
        await refresh_public_lists(
            interaction.client,
            gid,
            discord_guild=interaction.guild,
            unassigned=True,
            user_ids=[interaction.user.id],
        )

    @tree.command(name="drop", description="Drop one of your assigned tasks back to unassigned")
    @app_commands.describe(task_number="Number from your own task list")
    async def drop(interaction: discord.Interaction, task_number: app_commands.Range[int, 1, 999]) -> None:
        try:
            gid = _guild_id(interaction)
            task = svc.drop_task(gid, interaction.user.id, task_number)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await interaction.response.send_message(
            f"{interaction.user.mention} dropped **{task['description']}**."
        )
        await refresh_public_lists(
            interaction.client,
            gid,
            discord_guild=interaction.guild,
            unassigned=True,
            user_ids=[interaction.user.id],
        )

    @tree.command(name="mytasks", description="Show your assigned tasks (only you can see this)")
    async def mytasks(interaction: discord.Interaction) -> None:
        try:
            gid = _guild_id(interaction)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        view = build_mytasks_view(gid, interaction.user.id, offset=0)
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
        await interaction.response.defer(ephemeral=True)
        await _publish_or_update_daily_digest(
            interaction, gid, interaction.user, task["description"]
        )
        await refresh_public_lists(
            interaction.client,
            gid,
            discord_guild=interaction.guild,
            user_ids=[interaction.user.id],
        )
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            pass

    @tree.command(name="newtask", description="Add a new unassigned task")
    @app_commands.describe(description="What needs to be done")
    async def newtask(interaction: discord.Interaction, description: str) -> None:
        try:
            gid = _guild_id(interaction)
            svc.new_task(gid, description)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await _ack_and_refresh(interaction, gid, unassigned=True)

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
        await refresh_public_lists(
            interaction.client,
            gid,
            discord_guild=interaction.guild,
            unassigned=True,
            user_ids=[user.id],
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
            svc.unassign_task(gid, user.id, task_number)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await _ack_and_refresh(
            interaction, gid, unassigned=True, user_ids=[user.id]
        )

    @tree.command(name="removetask", description="Delete a task from the unassigned list")
    @app_commands.describe(task_number="Number from the unassigned list")
    async def removetask(interaction: discord.Interaction, task_number: app_commands.Range[int, 1, 999]) -> None:
        try:
            gid = _guild_id(interaction)
            svc.remove_task(gid, task_number)
        except svc.ServiceError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await _ack_and_refresh(interaction, gid, unassigned=True)
