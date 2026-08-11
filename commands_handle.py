from __future__ import annotations

import discord
from discord import app_commands

import tasks_service as svc
from announce import send_no_outstanding_announce
from config import PRIVILEGED_USERS
from render import refresh_public_lists, settings_text
from storage import get_guild, load_state


def _guild_id(interaction: discord.Interaction) -> int:
    if interaction.guild_id is None:
        raise svc.ServiceError("This command only works in a server.")
    return interaction.guild_id


def _check_privileged(interaction: discord.Interaction) -> None:
    owner_id = interaction.guild.owner_id if interaction.guild else None
    if not svc.is_privileged(interaction.user.id, owner_id, PRIVILEGED_USERS):
        raise svc.ServiceError("You are not allowed to use privileged commands.")


handle_group = app_commands.Group(
    name="handle",
    description="Configure please-handle (privileged)",
)


@handle_group.command(name="enable", description="Enable scheduled announces in this channel")
async def handle_enable(interaction: discord.Interaction) -> None:
    try:
        _check_privileged(interaction)
        gid = _guild_id(interaction)
        added = svc.enable_channel(gid, interaction.channel_id)
    except svc.ServiceError as e:
        await interaction.response.send_message(str(e), ephemeral=True)
        return
    if added:
        await interaction.response.send_message(
            f"Scheduled announces enabled in <#{interaction.channel_id}>."
        )
    else:
        await interaction.response.send_message(
            f"Already enabled in <#{interaction.channel_id}>."
        )


@handle_group.command(name="disable", description="Disable scheduled announces in this channel")
async def handle_disable(interaction: discord.Interaction) -> None:
    try:
        _check_privileged(interaction)
        gid = _guild_id(interaction)
        removed = svc.disable_channel(gid, interaction.channel_id)
    except svc.ServiceError as e:
        await interaction.response.send_message(str(e), ephemeral=True)
        return
    if removed:
        await interaction.response.send_message(
            f"Scheduled announces disabled in <#{interaction.channel_id}>."
        )
    else:
        await interaction.response.send_message(
            f"Was not enabled in <#{interaction.channel_id}>."
        )


@handle_group.command(name="schedule", description="Set announce schedule (e.g. MWF 1700)")
@app_commands.describe(
    days="Day letters MTWHFSU (Mon Tue Wed tHu Fri Sat sUn)",
    time="24-hour time as HHMM, e.g. 0900",
)
async def handle_schedule(interaction: discord.Interaction, days: str, time: str) -> None:
    try:
        _check_privileged(interaction)
        gid = _guild_id(interaction)
        d, t = svc.set_schedule(gid, days, time)
    except svc.ServiceError as e:
        await interaction.response.send_message(str(e), ephemeral=True)
        return
    await interaction.response.send_message(f"Schedule set to `{d} {t}`.")


@handle_group.command(name="timezone", description="Set timezone (e.g. America/New_York)")
@app_commands.describe(tz="IANA timezone name")
async def handle_timezone(interaction: discord.Interaction, tz: str) -> None:
    try:
        _check_privileged(interaction)
        gid = _guild_id(interaction)
        name = svc.set_timezone(gid, tz)
    except svc.ServiceError as e:
        await interaction.response.send_message(str(e), ephemeral=True)
        return
    await interaction.response.send_message(f"Timezone set to `{name}`.")


@handle_group.command(name="purge", description="Set purge age in days for completed tasks")
@app_commands.describe(age_in_days="Completed tasks older than this are purged")
async def handle_purge(
    interaction: discord.Interaction, age_in_days: app_commands.Range[int, 1, 3650]
) -> None:
    try:
        _check_privileged(interaction)
        gid = _guild_id(interaction)
        days = svc.set_purge_age(gid, age_in_days)
    except svc.ServiceError as e:
        await interaction.response.send_message(str(e), ephemeral=True)
        return
    await interaction.response.send_message(f"Purge age set to **{days}** days.")


@handle_group.command(name="force-purge", description="Purge all completed tasks now (ignores age)")
async def handle_force_purge(interaction: discord.Interaction) -> None:
    try:
        _check_privileged(interaction)
        gid = _guild_id(interaction)
        purged = svc.purge_completed(gid, force=True)
    except svc.ServiceError as e:
        await interaction.response.send_message(str(e), ephemeral=True)
        return
    if not purged:
        await interaction.response.send_message("Nothing to purge.")
        return
    lines = "\n".join(f"- {p['description']}" for p in purged[:20])
    extra = f"\n_…and {len(purged) - 20} more_" if len(purged) > 20 else ""
    await interaction.response.send_message(
        f"Purged **{len(purged)}** completed task(s):\n{lines}{extra}"
    )
    user_ids = sorted({p["assignee_id"] for p in purged if p.get("assignee_id")})
    await refresh_public_lists(
        interaction.client,
        gid,
        discord_guild=interaction.guild,
        unassigned=True,
        user_ids=user_ids,
    )


@handle_group.command(name="settings", description="Print current please-handle settings")
async def handle_settings(interaction: discord.Interaction) -> None:
    try:
        _check_privileged(interaction)
        gid = _guild_id(interaction)
    except svc.ServiceError as e:
        await interaction.response.send_message(str(e), ephemeral=True)
        return
    await interaction.response.send_message(settings_text(gid))


@handle_group.command(name="recent-purged", description="Show recently purged tasks")
async def handle_recent_purged(interaction: discord.Interaction) -> None:
    try:
        _check_privileged(interaction)
        gid = _guild_id(interaction)
    except svc.ServiceError as e:
        await interaction.response.send_message(str(e), ephemeral=True)
        return
    state = load_state()
    guild = get_guild(state, gid)
    recent = guild.get("recent_purged") or []
    if not recent:
        await interaction.response.send_message("No recently purged tasks.")
        return
    # show newest last in buffer; display newest first
    lines = []
    for p in reversed(recent[-30:]):
        who = f"<@{p['assignee_id']}>" if p.get("assignee_id") else "unassigned"
        lines.append(f"- {p['description']} (was {who}, completed `{p.get('completed_at')}`)")
    await interaction.response.send_message("**Recently purged:**\n" + "\n".join(lines))


handle_test_group = app_commands.Group(
    name="test",
    description="Privileged test helpers",
    parent=handle_group,
)


@handle_test_group.command(
    name="no-tasks-announce",
    description="Post the no-outstanding-tasks announce message in this channel",
)
async def test_no_tasks_announce(interaction: discord.Interaction) -> None:
    try:
        _check_privileged(interaction)
        _guild_id(interaction)
    except svc.ServiceError as e:
        await interaction.response.send_message(str(e), ephemeral=True)
        return

    channel = interaction.channel
    if channel is None or not isinstance(channel, discord.abc.Messageable):
        await interaction.response.send_message(
            "Cannot post an announce here.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    await send_no_outstanding_announce(channel)
    await interaction.followup.send("Posted no-tasks announce.", ephemeral=True)


async def setup_handle_commands(tree: app_commands.CommandTree) -> None:
    tree.add_command(handle_group)
